import os
import hashlib
import secrets
from datetime import datetime, timedelta
from mysql_db import get_connection


# ─────────────────────────────────────────────
# CONNECTION
# ─────────────────────────────────────────────
def get_conn():
    return get_connection()


# ─────────────────────────────────────────────
# INIT TABLES
# ─────────────────────────────────────────────
def init_new_tables():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS faculty (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_verified INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS otp_store (
            id INT AUTO_INCREMENT PRIMARY KEY,
            target VARCHAR(255) NOT NULL,
            otp_code VARCHAR(10) NOT NULL,
            purpose VARCHAR(50) NOT NULL,
            expires_at DATETIME NOT NULL,
            used INT DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            reg_number VARCHAR(255) UNIQUE NOT NULL,
            college_email VARCHAR(255) UNIQUE NOT NULL,
            phone VARCHAR(20) NOT NULL,
            password_hash TEXT NOT NULL,
            folder_name VARCHAR(255) NOT NULL,
            registered_by VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance_sessions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            faculty_email VARCHAR(255) NOT NULL,
            session_date VARCHAR(20) NOT NULL,
            start_time VARCHAR(20) NOT NULL,
            end_time VARCHAR(20) NOT NULL,
            attendance_type VARCHAR(20) DEFAULT 'normal',
            is_active INT DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# PASSWORD + OTP HELPERS
# ─────────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = os.environ.get("PASSWORD_SALT", "dev_salt")
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def generate_otp(length: int = 6) -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


# ─────────────────────────────────────────────
# FACULTY FUNCTIONS
# ─────────────────────────────────────────────
def faculty_exists(email: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM faculty WHERE email=%s", (email,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def create_faculty(name: str, email: str, password: str) -> dict:
    if faculty_exists(email):
        return {"ok": False, "msg": "Email already registered."}

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO faculty (name, email, password_hash, is_verified) VALUES (%s,%s,%s,%s)",
        (name, email, hash_password(password), 1)
    )
    conn.commit()
    conn.close()
    return {"ok": True, "msg": "Faculty account created successfully."}


def authenticate_faculty(email: str, password: str) -> dict:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, email FROM faculty WHERE email=%s AND password_hash=%s",
        (email, hash_password(password))
    )
    row = cur.fetchone()
    conn.close()

    if row is None:
        return {"ok": False, "msg": "Invalid email or password.", "faculty": None}

    return {
        "ok": True,
        "msg": "Login successful.",
        "faculty": {"id": row[0], "name": row[1], "email": row[2]}
    }


def get_faculty_by_email(email: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email FROM faculty WHERE email=%s", (email,))
    row = cur.fetchone()
    conn.close()
    return row


def update_faculty_password(email: str, new_password: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE faculty SET password_hash=%s WHERE email=%s",
        (hash_password(new_password), email)
    )
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# OTP SYSTEM
# ─────────────────────────────────────────────
def save_otp(target: str, otp_code: str, purpose: str, ttl_minutes: int = 10):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "UPDATE otp_store SET used=1 WHERE target=%s AND purpose=%s AND used=0",
        (target, purpose)
    )

    expires_at = datetime.now() + timedelta(minutes=ttl_minutes)

    cur.execute(
        "INSERT INTO otp_store (target, otp_code, purpose, expires_at) VALUES (%s,%s,%s,%s)",
        (target, otp_code, purpose, expires_at)
    )

    conn.commit()
    conn.close()


def verify_otp(target: str, otp_code: str, purpose: str) -> dict:
    conn = get_conn()
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


# ─────────────────────────────────────────────
# STUDENT FUNCTIONS
# ─────────────────────────────────────────────
def register_student(name, reg_number, college_email, phone,
                     folder_name, password=None, registered_by=None):

    if password is None:
        password = "student123"

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO students
            (name, reg_number, college_email, phone, password_hash, folder_name, registered_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            name,
            reg_number,
            college_email,
            phone,
            hash_password(password),
            folder_name,
            registered_by
        ))

        conn.commit()
        conn.close()
        return {"ok": True, "msg": "Student registered successfully."}

    except Exception as e:
        conn.close()
        return {"ok": False, "msg": str(e)}


def authenticate_student(email: str, password: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, name, college_email, reg_number, phone
        FROM students
        WHERE college_email=%s AND password_hash=%s
    """, (email, hash_password(password)))

    row = cur.fetchone()
    conn.close()

    if row is None:
        return {"ok": False, "msg": "Invalid email or password.", "student": None}

    return {
        "ok": True,
        "msg": "Login successful.",
        "student": {
            "id": row[0],
            "name": row[1],
            "email": row[2],
            "reg_number": row[3],
            "phone": row[4]
        }
    }


def get_student_by_email(email: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, college_email, reg_number, phone
        FROM students
        WHERE college_email=%s
    """, (email,))
    row = cur.fetchone()
    conn.close()
    return row


def update_student_password(email: str, new_password: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE students SET password_hash=%s WHERE college_email=%s",
        (hash_password(new_password), email)
    )
    conn.commit()
    conn.close()


def get_all_students():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, reg_number, college_email, phone, folder_name, created_at
        FROM students
        ORDER BY name
    """)
    rows = cur.fetchall()
    conn.close()

    formatted_rows = []
    for row in rows:
        row = list(row)
        if row[6] is not None:
            row[6] = row[6].strftime("%Y-%m-%d %H:%M:%S")
        formatted_rows.append(tuple(row))

    return formatted_rows


def get_student_phones():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT phone, name FROM students")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_student_emails():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT college_email, name FROM students")
    rows = cur.fetchall()
    conn.close()
    return rows


# ─────────────────────────────────────────────
# SESSION SYSTEM
# ─────────────────────────────────────────────
def create_session(faculty_email, session_date, start_time, end_time):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE attendance_sessions
        SET is_active=0
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

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, start_time, end_time
        FROM attendance_sessions
        WHERE session_date=%s AND is_active=1
        ORDER BY id DESC LIMIT 1
    """, (session_date,))

    session = cur.fetchone()
    conn.close()

    if session is None:
        return {"has_session": False}

    now_time = datetime.now().strftime("%H:%M")
    start_time = session[1][:5]
    end_time = session[2][:5]

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
        "session_id": session[0]
    }