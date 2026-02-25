"""
app_extension.py  –  New Feature Routes (Faculty Auth + Student Auth + Student Registry + Sessions)
======================================================================================
This file attaches as a Flask Blueprint to your existing app.py.
All new routes start with /faculty/ or /student/ so they never conflict with existing routes.

Two lines to add in app.py (before  if __name__ == "__main__"):
    from app_extension import ext_bp
    app.register_blueprint(ext_bp)
"""

from flask import (Blueprint, render_template, request, redirect,
                   session, jsonify)
from datetime import datetime, date
import auth_db

ext_bp = Blueprint("ext", __name__, template_folder="templates")

# Ensure all new tables exist the moment this file is imported
auth_db.init_new_tables()


# ════════════════════════════════════════════
#  HELPER DECORATORS
# ════════════════════════════════════════════
def faculty_required(f):
    """Redirect to /faculty/login if faculty is not logged in."""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "faculty_user" not in session:
            return redirect("/faculty/login")
        return f(*args, **kwargs)
    return wrapper


def student_required(f):
    """Redirect to /student/login if student is not logged in."""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "student_user" not in session:
            return redirect("/student/login")
        return f(*args, **kwargs)
    return wrapper


# ════════════════════════════════════════════
#  FACULTY SIGNUP
# ════════════════════════════════════════════
@ext_bp.route("/faculty/signup", methods=["GET", "POST"])
def faculty_signup():
    if request.method == "GET":
        return render_template("faculty_signup.html")

    name     = request.form.get("name", "").strip()
    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm  = request.form.get("confirm_password", "")

    if not name or not email or not password:
        return render_template("faculty_signup.html", error="All fields are required.")
    if password != confirm:
        return render_template("faculty_signup.html", error="Passwords do not match.")
    if len(password) < 6:
        return render_template("faculty_signup.html",
                               error="Password must be at least 6 characters.")

    result = auth_db.create_faculty(name, email, password)
    if not result["ok"]:
        return render_template("faculty_signup.html", error=result["msg"])

    return render_template("faculty_login.html",
                           success="Account created successfully. Please log in.")



# ════════════════════════════════════════════
#  FACULTY LOGIN
# ════════════════════════════════════════════
@ext_bp.route("/faculty/login", methods=["GET", "POST"])
def faculty_login():
    if "faculty_user" in session:
        return redirect("/faculty/schedule")

    if request.method == "GET":
        return render_template("faculty_login.html")

    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    result = auth_db.authenticate_faculty(email, password)
    if not result["ok"]:
        return render_template("faculty_login.html", error=result["msg"])

    session["faculty_user"] = result["faculty"]
    return redirect("/faculty/schedule")


# ════════════════════════════════════════════
#  RESET PASSWORD (direct — no OTP)
# ════════════════════════════════════════════
@ext_bp.route("/faculty/reset-password", methods=["POST"])
def faculty_reset_password():
    email        = request.form.get("reset_email", "").strip().lower()
    new_password = request.form.get("new_password", "")
    confirm      = request.form.get("confirm_password", "")

    if not email or not new_password or not confirm:
        return render_template("faculty_login.html",
                               reset_error="All fields are required.")

    faculty = auth_db.get_faculty_by_email(email)
    if faculty is None:
        return render_template("faculty_login.html",
                               reset_error="No account found with that email.")

    if new_password != confirm:
        return render_template("faculty_login.html",
                               reset_error="Passwords do not match.")

    if len(new_password) < 6:
        return render_template("faculty_login.html",
                               reset_error="Password must be at least 6 characters.")

    auth_db.update_faculty_password(email, new_password)
    return render_template("faculty_login.html",
                           success="Password reset successful. Please log in.")


# ════════════════════════════════════════════
#  FACULTY LOGOUT
# ════════════════════════════════════════════
@ext_bp.route("/faculty/logout", methods=["POST", "GET"])
def faculty_logout():
    session.pop("faculty_user", None)
    return redirect("/faculty/login")


# ════════════════════════════════════════════
#  ATTENDANCE SCHEDULE
# ════════════════════════════════════════════
@ext_bp.route("/faculty/schedule", methods=["GET", "POST"])
@faculty_required
def faculty_schedule():
    faculty = session["faculty_user"]
    today   = date.today().isoformat()
    status  = auth_db.get_session_status(today)
    message = None
    error   = None

    if request.method == "POST":
        start_time = request.form.get("start_time", "").strip()   # HH:MM from <input type="time">
        end_time   = request.form.get("end_time",   "").strip()   # HH:MM

        if not start_time or not end_time:
            error = "Both start and end times are required."
        elif start_time >= end_time:
            error = "End time must be after start time."
        else:
            result = auth_db.create_session(
                faculty_email=faculty["email"],
                session_date=today,
                start_time=start_time + ":00",
                end_time=end_time + ":00"
            )
            if result["ok"]:
                message = f"Session created! Normal attendance open until {end_time}."
                status = auth_db.get_session_status(today)
            else:
                error = "Failed to create session."

    return render_template("faculty_schedule.html",
                           faculty=faculty,
                           today=today,
                           status=status,
                           message=message,
                           error=error)


# ════════════════════════════════════════════
#  STUDENT LIST
# ════════════════════════════════════════════
@ext_bp.route("/faculty/students")
@faculty_required
def faculty_students():
    students = auth_db.get_all_students()
    return render_template("faculty_students.html",
                           students=students,
                           faculty=session["faculty_user"])


# ════════════════════════════════════════════
#  STUDENT REGISTRATION (by Faculty)
# ════════════════════════════════════════════
@ext_bp.route("/faculty/register-student", methods=["GET", "POST"])
@faculty_required
def register_student_faculty():
    faculty = session["faculty_user"]

    if request.method == "GET":
        return render_template("faculty_register_student.html", faculty=faculty)

    name          = request.form.get("name",          "").strip()
    reg_number    = request.form.get("reg_number",    "").strip().upper()
    college_email = request.form.get("college_email", "").strip().lower()
    phone         = request.form.get("phone",         "").strip()

    if not name or not reg_number or not college_email or not phone:
        return render_template("faculty_register_student.html",
                               faculty=faculty,
                               error="All fields are required.")

    # folder_name matches how camera.py creates dataset/<name>/
    # No password needed - faculty is registering on behalf of student
    result = auth_db.register_student(
        name=name,
        reg_number=reg_number,
        college_email=college_email,
        phone=phone,
        folder_name=name,
        password=None,  # Will use default password
        registered_by=faculty["email"]
    )

    if result["ok"]:
        return render_template("faculty_register_student.html",
                               faculty=faculty,
                               success=(f"Student '{name}' registered with default password 'student123'. "
                                        f"Now capture their face on the camera dashboard."))
    else:
        return render_template("faculty_register_student.html",
                               faculty=faculty,
                               error=result["msg"])


# ════════════════════════════════════════════
#  STUDENT SELF-REGISTRATION
# ════════════════════════════════════════════
@ext_bp.route("/student/register", methods=["GET", "POST"])
def student_register():
    if request.method == "GET":
        return render_template("student_register.html")

    name          = request.form.get("name", "").strip()
    reg_number    = request.form.get("reg_number", "").strip().upper()
    college_email = request.form.get("college_email", "").strip().lower()
    phone         = request.form.get("phone", "").strip()
    password      = request.form.get("password", "")
    confirm       = request.form.get("confirm_password", "")

    if not all([name, reg_number, college_email, phone, password]):
        return render_template("student_register.html", 
                             error="All fields are required.")
    
    if password != confirm:
        return render_template("student_register.html", 
                             error="Passwords do not match.")
    
    if len(password) < 6:
        return render_template("student_register.html",
                             error="Password must be at least 6 characters.")

    # Register student with their chosen password
    result = auth_db.register_student(
        name=name,
        reg_number=reg_number,
        college_email=college_email,
        phone=phone,
        folder_name=name,
        password=password,
        registered_by="self"
    )

    if result["ok"]:
        return render_template("student_register.html",
                             success="Registration successful! You can now login and register your face.")
    else:
        return render_template("student_register.html", error=result["msg"])


# ════════════════════════════════════════════
#  STUDENT LOGIN
# ════════════════════════════════════════════
@ext_bp.route("/student/login", methods=["GET", "POST"])
def student_login():
    if "student_user" in session:
        return redirect("/student/dashboard")

    if request.method == "GET":
        return render_template("student_login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    result = auth_db.authenticate_student(email, password)
    if not result["ok"]:
        return render_template("student_login.html", error=result["msg"])

    session["student_user"] = result["student"]
    return redirect("/student/dashboard")


# ════════════════════════════════════════════
#  STUDENT RESET PASSWORD (direct — no OTP)
# ════════════════════════════════════════════
@ext_bp.route("/student/reset-password", methods=["POST"])
def student_reset_password():
    email        = request.form.get("reset_email", "").strip().lower()
    new_password = request.form.get("new_password", "")
    confirm      = request.form.get("confirm_password", "")

    if not email or not new_password or not confirm:
        return render_template("student_login.html",
                               reset_error="All fields are required.")

    student = auth_db.get_student_by_email(email)
    if student is None:
        return render_template("student_login.html",
                               reset_error="No account found with that email.")

    if new_password != confirm:
        return render_template("student_login.html",
                               reset_error="Passwords do not match.")

    if len(new_password) < 6:
        return render_template("student_login.html",
                               reset_error="Password must be at least 6 characters.")

    auth_db.update_student_password(email, new_password)
    return render_template("student_login.html",
                           success="Password reset successful. Please log in.")


# ════════════════════════════════════════════
#  STUDENT DASHBOARD
# ════════════════════════════════════════════
@ext_bp.route("/student/dashboard")
@student_required
def student_dashboard():
    student = session["student_user"]
    today = date.today().isoformat()
    status = auth_db.get_session_status(today)
    
    return render_template("student_dashboard.html", 
                         student=student,
                         session_status=status)


# ════════════════════════════════════════════
#  STUDENT LOGOUT
# ════════════════════════════════════════════
@ext_bp.route("/student/logout", methods=["POST", "GET"])
def student_logout():
    session.pop("student_user", None)
    return redirect("/student/login")


# ════════════════════════════════════════════
#  API: SESSION STATUS  (JSON – polled by dashboard)
# ════════════════════════════════════════════
@ext_bp.route("/api/session-status")
def api_session_status():
    """
    JSON endpoint for dashboard.html to poll.
    Returns current mode so the UI can freeze normal attendance after deadline.

    Response:
    {
      "has_session": true | false,
      "mode":        "before" | "normal" | "late",
      "start_time":  "09:00",
      "end_time":    "09:30",
      "now":         "09:45"
    }
    """
    today  = date.today().isoformat()
    status = auth_db.get_session_status(today)
    now    = datetime.now().strftime("%H:%M")
    return jsonify({
        "has_session": status["has_session"],
        "mode":        status.get("mode", "before"),
        "start_time":  status.get("start_time", ""),
        "end_time":    status.get("end_time", ""),
        "now":         now
    })


# ════════════════════════════════════════════
#  STUDENT EDIT (by Faculty)
# ════════════════════════════════════════════
@ext_bp.route("/faculty/edit-student/<int:student_id>", methods=["GET", "POST"])
@faculty_required
def edit_student(student_id):
    faculty = session["faculty_user"]
    conn = auth_db.get_conn()
    cur = conn.cursor()

    if request.method == "POST":
        name          = request.form.get("name", "").strip()
        reg_number    = request.form.get("reg_number", "").strip().upper()
        college_email = request.form.get("college_email", "").strip().lower()
        phone         = request.form.get("phone", "").strip()

        if not name or not reg_number or not college_email or not phone:
            cur.execute("SELECT id, name, reg_number, college_email, phone FROM students WHERE id=%s", (student_id,))
            student = cur.fetchone()
            conn.close()
            return render_template("faculty_edit_student.html", faculty=faculty,
                                   student=student, error="All fields are required.")

        cur.execute("""
            UPDATE students SET name=%s, reg_number=%s, college_email=%s, phone=%s, folder_name=%s
            WHERE id=%s
        """, (name, reg_number, college_email, phone, name, student_id))
        conn.commit()
        conn.close()
        return redirect("/faculty/students")

    cur.execute("SELECT id, name, reg_number, college_email, phone FROM students WHERE id=%s", (student_id,))
    student = cur.fetchone()
    conn.close()

    if student is None:
        return redirect("/faculty/students")

    return render_template("faculty_edit_student.html", faculty=faculty, student=student)


# ════════════════════════════════════════════
#  STUDENT DELETE (by Faculty)
# ════════════════════════════════════════════
@ext_bp.route("/faculty/delete-student/<int:student_id>", methods=["POST"])
@faculty_required
def delete_student(student_id):
    conn = auth_db.get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM students WHERE id=%s", (student_id,))
    conn.commit()
    conn.close()
    return redirect("/faculty/students")
