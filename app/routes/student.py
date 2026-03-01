"""
Student routes — register, login, password reset, dashboard.
"""

from functools import wraps
from datetime import date, datetime

from flask import Blueprint, render_template, request, redirect, session, jsonify

from app import auth

student_bp = Blueprint("student", __name__)


def student_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "student_user" not in session:
            return redirect("/student/login")
        return f(*args, **kwargs)
    return wrapper


# ── Self-registration ───────────────────────────────────────────────

@student_bp.route("/student/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("student/register.html")

    name = request.form.get("name", "").strip()
    reg_number = request.form.get("reg_number", "").strip().upper()
    college_email = request.form.get("college_email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")

    if not all([name, reg_number, college_email, phone, password]):
        return render_template("student/register.html",
                               error="All fields are required.")
    if password != confirm:
        return render_template("student/register.html",
                               error="Passwords do not match.")
    if len(password) < 6:
        return render_template("student/register.html",
                               error="Password must be at least 6 characters.")

    result = auth.register_student(
        name=name, reg_number=reg_number, college_email=college_email,
        phone=phone, folder_name=name, password=password, registered_by="self",
    )
    if result["ok"]:
        return render_template("student/register.html",
                               success="Registration successful! You can now login.")
    return render_template("student/register.html", error=result["msg"])


# ── Login ───────────────────────────────────────────────────────────

@student_bp.route("/student/login", methods=["GET", "POST"])
def login():
    if "student_user" in session:
        return redirect("/student/dashboard")

    if request.method == "GET":
        return render_template("student/login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    result = auth.authenticate_student(email, password)
    if not result["ok"]:
        return render_template("student/login.html", error=result["msg"])

    session["student_user"] = result["student"]
    return redirect("/student/dashboard")


# ── Reset password ──────────────────────────────────────────────────

@student_bp.route("/student/reset-password", methods=["POST"])
def reset_password():
    email = request.form.get("reset_email", "").strip().lower()
    new_password = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")

    if not email or not new_password or not confirm:
        return render_template("student/login.html",
                               reset_error="All fields are required.")
    if auth.get_student_by_email(email) is None:
        return render_template("student/login.html",
                               reset_error="No account found with that email.")
    if new_password != confirm:
        return render_template("student/login.html",
                               reset_error="Passwords do not match.")
    if len(new_password) < 6:
        return render_template("student/login.html",
                               reset_error="Password must be at least 6 characters.")

    auth.update_student_password(email, new_password)
    return render_template("student/login.html",
                           success="Password reset successful. Please log in.")


# ── Dashboard ───────────────────────────────────────────────────────

@student_bp.route("/student/dashboard")
@student_required
def dashboard():
    student = session["student_user"]
    today = date.today().isoformat()
    status = auth.get_session_status(today)
    return render_template("student/dashboard.html",
                           student=student, session_status=status)


# ── Logout ──────────────────────────────────────────────────────────

@student_bp.route("/student/logout", methods=["POST", "GET"])
def logout():
    session.pop("student_user", None)
    return redirect("/student/login")


# ── API: session status (polled by dashboard JS) ────────────────────

@student_bp.route("/api/session-status")
def api_session_status():
    today = date.today().isoformat()
    status = auth.get_session_status(today)
    now = datetime.now().strftime("%H:%M")
    return jsonify({
        "has_session": status["has_session"],
        "mode": status.get("mode", "before"),
        "start_time": status.get("start_time", ""),
        "end_time": status.get("end_time", ""),
        "now": now,
    })
