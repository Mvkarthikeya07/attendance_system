"""
Faculty routes — signup, login, password reset, schedule, student management.
"""

from functools import wraps
from datetime import date

from flask import Blueprint, render_template, request, redirect, session, jsonify

from app import auth
from app.database import get_connection

faculty_bp = Blueprint("faculty", __name__)


def faculty_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "faculty_user" not in session:
            return redirect("/faculty/login")
        return f(*args, **kwargs)
    return wrapper


# ── Signup ──────────────────────────────────────────────────────────

@faculty_bp.route("/faculty/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("faculty/signup.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")

    if not name or not email or not password:
        return render_template("faculty/signup.html", error="All fields are required.")
    if password != confirm:
        return render_template("faculty/signup.html", error="Passwords do not match.")
    if len(password) < 6:
        return render_template("faculty/signup.html",
                               error="Password must be at least 6 characters.")

    result = auth.create_faculty(name, email, password)
    if not result["ok"]:
        return render_template("faculty/signup.html", error=result["msg"])

    return render_template("faculty/login.html",
                           success="Account created. Please log in.")


# ── Login ───────────────────────────────────────────────────────────

@faculty_bp.route("/faculty/login", methods=["GET", "POST"])
def login():
    if "faculty_user" in session:
        return redirect("/faculty/schedule")

    if request.method == "GET":
        return render_template("faculty/login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    result = auth.authenticate_faculty(email, password)
    if not result["ok"]:
        return render_template("faculty/login.html", error=result["msg"])

    session["faculty_user"] = result["faculty"]
    return redirect("/faculty/schedule")


# ── Reset password ──────────────────────────────────────────────────

@faculty_bp.route("/faculty/reset-password", methods=["POST"])
def reset_password():
    email = request.form.get("reset_email", "").strip().lower()
    new_password = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")

    if not email or not new_password or not confirm:
        return render_template("faculty/login.html",
                               reset_error="All fields are required.")
    if auth.get_faculty_by_email(email) is None:
        return render_template("faculty/login.html",
                               reset_error="No account found with that email.")
    if new_password != confirm:
        return render_template("faculty/login.html",
                               reset_error="Passwords do not match.")
    if len(new_password) < 6:
        return render_template("faculty/login.html",
                               reset_error="Password must be at least 6 characters.")

    auth.update_faculty_password(email, new_password)
    return render_template("faculty/login.html",
                           success="Password reset successful. Please log in.")


# ── Logout ──────────────────────────────────────────────────────────

@faculty_bp.route("/faculty/logout", methods=["POST", "GET"])
def logout():
    session.pop("faculty_user", None)
    return redirect("/faculty/login")


# ── Schedule ────────────────────────────────────────────────────────

@faculty_bp.route("/faculty/schedule", methods=["GET", "POST"])
@faculty_required
def schedule():
    faculty = session["faculty_user"]
    today = date.today().isoformat()
    status = auth.get_session_status(today)
    message = error = None

    if request.method == "POST":
        start_time = request.form.get("start_time", "").strip()
        end_time = request.form.get("end_time", "").strip()

        if not start_time or not end_time:
            error = "Both start and end times are required."
        elif start_time >= end_time:
            error = "End time must be after start time."
        else:
            result = auth.create_session(
                faculty_email=faculty["email"],
                session_date=today,
                start_time=start_time + ":00",
                end_time=end_time + ":00",
            )
            if result["ok"]:
                message = f"Session created! Attendance open until {end_time}."
                status = auth.get_session_status(today)
            else:
                error = "Failed to create session."

    return render_template("faculty/schedule.html",
                           faculty=faculty, today=today,
                           status=status, message=message, error=error)


# ── Student list ────────────────────────────────────────────────────

@faculty_bp.route("/faculty/students")
@faculty_required
def students():
    students_list = auth.get_all_students()
    return render_template("faculty/students.html",
                           students=students_list,
                           faculty=session["faculty_user"])


# ── Register student ────────────────────────────────────────────────

@faculty_bp.route("/faculty/register-student", methods=["GET", "POST"])
@faculty_required
def register_student():
    faculty = session["faculty_user"]

    if request.method == "GET":
        return render_template("faculty/register_student.html", faculty=faculty)

    name = request.form.get("name", "").strip()
    reg_number = request.form.get("reg_number", "").strip().upper()
    college_email = request.form.get("college_email", "").strip().lower()
    phone = request.form.get("phone", "").strip()

    if not all([name, reg_number, college_email, phone]):
        return render_template("faculty/register_student.html",
                               faculty=faculty, error="All fields are required.")

    result = auth.register_student(
        name=name, reg_number=reg_number, college_email=college_email,
        phone=phone, folder_name=name, password=None,
        registered_by=faculty["email"],
    )

    if result["ok"]:
        return render_template("faculty/register_student.html", faculty=faculty,
                               success=f"Student '{name}' registered (default password: student123).")
    return render_template("faculty/register_student.html",
                           faculty=faculty, error=result["msg"])


# ── Edit student ────────────────────────────────────────────────────

@faculty_bp.route("/faculty/edit-student/<int:student_id>", methods=["GET", "POST"])
@faculty_required
def edit_student(student_id):
    faculty = session["faculty_user"]
    conn = get_connection()
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        reg_number = request.form.get("reg_number", "").strip().upper()
        college_email = request.form.get("college_email", "").strip().lower()
        phone = request.form.get("phone", "").strip()

        if not all([name, reg_number, college_email, phone]):
            cur.execute(
                "SELECT id, name, reg_number, college_email, phone FROM students WHERE id=%s",
                (student_id,),
            )
            student = cur.fetchone()
            conn.close()
            return render_template("faculty/edit_student.html",
                                   faculty=faculty, student=student,
                                   error="All fields are required.")

        cur.execute("""
            UPDATE students SET name=%s, reg_number=%s, college_email=%s, phone=%s, folder_name=%s
            WHERE id=%s
        """, (name, reg_number, college_email, phone, name, student_id))
        conn.commit()
        conn.close()
        return redirect("/faculty/students")

    cur.execute(
        "SELECT id, name, reg_number, college_email, phone FROM students WHERE id=%s",
        (student_id,),
    )
    student = cur.fetchone()
    conn.close()
    if student is None:
        return redirect("/faculty/students")
    return render_template("faculty/edit_student.html",
                           faculty=faculty, student=student)


# ── Delete student ──────────────────────────────────────────────────

@faculty_bp.route("/faculty/delete-student/<int:student_id>", methods=["POST"])
@faculty_required
def delete_student(student_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM students WHERE id=%s", (student_id,))
    conn.commit()
    conn.close()
    return redirect("/faculty/students")
