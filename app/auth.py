"""
Authentication helpers — faculty, student, OTP, and session operations.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from app.config import PASSWORD_SALT
from app.database import get_connection


# ── Password / OTP helpers ──────────────────────────────────────────

def hash_password(password: str) -> str:
    return hashlib.sha256(f"{PASSWORD_SALT}{password}".encode()).hexdigest()


def generate_otp(length: int = 6) -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


# ── Faculty ─────────────────────────────────────────────────────────

def faculty_exists(email: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM faculty WHERE email=%s", (email,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def create_faculty(name: str, email: str, password: str) -> dict:
    if faculty_exists(email):
        return {"ok": False, "msg": "Email already registered."}

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO faculty (name, email, password_hash, is_verified) VALUES (%s,%s,%s,%s)",
        (name, email, hash_password(password), 1),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "msg": "Faculty account created successfully."}


def authenticate_faculty(email: str, password: str) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, email FROM faculty WHERE email=%s AND password_hash=%s",
        (email, hash_password(password)),
    )
    row = cur.fetchone()
    conn.close()

    if row is None:
        return {"ok": False, "msg": "Invalid email or password.", "faculty": None}

    return {
        "ok": True,
        "msg": "Login successful.",
        "faculty": {"id": row[0], "name": row[1], "email": row[2]},
    }


def get_faculty_by_email(email: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email FROM faculty WHERE email=%s", (email,))
    row = cur.fetchone()
    conn.close()
    return row


def update_faculty_password(email: str, new_password: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE faculty SET password_hash=%s WHERE email=%s",
        (hash_password(new_password), email),
    )
    conn.commit()
    conn.close()


# ── Students ────────────────────────────────────────────────────────

def register_student(name, reg_number, college_email, phone,
                     folder_name, password=None, registered_by=None):
    if password is None:
        password = "student123"

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO students
            (name, reg_number, college_email, phone, password_hash, folder_name, registered_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (name, reg_number, college_email, phone,
              hash_password(password), folder_name, registered_by))
        conn.commit()
        return {"ok": True, "msg": "Student registered successfully."}
    except Exception as e:
        return {"ok": False, "msg": str(e)}
    finally:
        conn.close()


def authenticate_student(email: str, password: str) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, college_email, reg_number, phone
        FROM students WHERE college_email=%s AND password_hash=%s
    """, (email, hash_password(password)))
    row = cur.fetchone()
    conn.close()

    if row is None:
        return {"ok": False, "msg": "Invalid email or password.", "student": None}

    return {
        "ok": True,
        "msg": "Login successful.",
        "student": {
            "id": row[0], "name": row[1], "email": row[2],
            "reg_number": row[3], "phone": row[4],
        },
    }


def get_student_by_email(email: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, college_email, reg_number, phone FROM students WHERE college_email=%s",
        (email,),
    )
    row = cur.fetchone()
    conn.close()
    return row


def update_student_password(email: str, new_password: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE students SET password_hash=%s WHERE college_email=%s",
        (hash_password(new_password), email),
    )
    conn.commit()
    conn.close()


def get_all_students():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, reg_number, college_email, phone, folder_name, created_at
        FROM students ORDER BY name
    """)
    rows = cur.fetchall()
    conn.close()

    formatted = []
    for row in rows:
        row = list(row)
        if row[6] is not None:
            row[6] = row[6].strftime("%Y-%m-%d %H:%M:%S")
        formatted.append(tuple(row))
    return formatted


def get_student_phones():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT phone, name FROM students")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_student_emails():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT college_email, name FROM students")
    rows = cur.fetchall()
    conn.close()
    return rows


# ── OTP ─────────────────────────────────────────────────────────────

def save_otp(target: str, otp_code: str, purpose: str, ttl_minutes: int = 10):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE otp_store SET used=1 WHERE target=%s AND purpose=%s AND used=0",
        (target, purpose),
    )
    expires_at = datetime.now() + timedelta(minutes=ttl_minutes)
    cur.execute(
        "INSERT INTO otp_store (target, otp_code, purpose, expires_at) VALUES (%s,%s,%s,%s)",
        (target, otp_code, purpose, expires_at),
    )
    conn.commit()
    conn.close()


def verify_otp(target: str, otp_code: str, purpose: str) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, expires_at FROM otp_store
        WHERE target=%s AND otp_code=%s AND purpose=%s AND used=0
        ORDER BY id DESC LIMIT 1
    """, (target, otp_code, purpose))
    row = cur.fetchone()

    if row is None:
        conn.close()
        return {"ok": False, "msg": "Invalid OTP."}

    if datetime.now() > row[1]:
        conn.close()
        return {"ok": False, "msg": "OTP expired."}

    cur.execute("UPDATE otp_store SET used=1 WHERE id=%s", (row[0],))
    conn.commit()
    conn.close()
    return {"ok": True, "msg": "OTP verified."}


# ── Attendance Sessions ─────────────────────────────────────────────

def create_session(faculty_email, session_date, start_time, end_time):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE attendance_sessions SET is_active=0
        WHERE session_date=%s AND faculty_email=%s
    """, (session_date, faculty_email))
    cur.execute("""
        INSERT INTO attendance_sessions
        (faculty_email, session_date, start_time, end_time, attendance_type, is_active)
        VALUES (%s,%s,%s,%s,'normal',1)
    """, (faculty_email, session_date, start_time, end_time))
    conn.commit()
    session_id = cur.lastrowid
    conn.close()
    return {"ok": True, "session_id": session_id}


def get_session_status(session_date=None):
    if session_date is None:
        session_date = datetime.now().strftime("%Y-%m-%d")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, start_time, end_time FROM attendance_sessions
        WHERE session_date=%s AND is_active=1
        ORDER BY id DESC LIMIT 1
    """, (session_date,))
    row = cur.fetchone()
    conn.close()

    if row is None:
        return {"has_session": False}

    now_time = datetime.now().strftime("%H:%M")
    start_time = row[1][:5]
    end_time = row[2][:5]

    if now_time < start_time:
        mode = "before"
    elif start_time <= now_time <= end_time:
        mode = "normal"
    else:
        mode = "late"

    return {
        "has_session": True,
        "mode": mode,
        "start_time": start_time,
        "end_time": end_time,
        "session_id": row[0],
    }
