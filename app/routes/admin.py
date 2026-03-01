"""
Admin routes — login, menu, attendance records, CSV download.
"""

import io
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect,
    session, jsonify, make_response,
)

from app.database import get_connection

admin_bp = Blueprint("admin", __name__)


# ── Decorators ──────────────────────────────────────────────────────

def login_required(f):
    """Any authenticated user (admin / faculty / student)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not any(k in session for k in ("user", "faculty_user", "student_user")):
            return redirect("/")
        return f(*args, **kwargs)
    return wrapper


def admin_or_faculty_required(f):
    """Admin or faculty only."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session and "faculty_user" not in session:
            return redirect("/")
        return f(*args, **kwargs)
    return wrapper


# ── Pages ───────────────────────────────────────────────────────────

@admin_bp.route("/")
def index():
    if "user" in session:
        return redirect("/menu")
    return render_template("index.html")


@admin_bp.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    if username == "admin" and password == "admin":
        session["user"] = username
        return jsonify({"success": True})
    return jsonify({"success": False})


@admin_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    return redirect("/")


@admin_bp.route("/menu")
def menu():
    if "user" not in session:
        return redirect("/")
    return render_template("menu.html")


# ── Records ─────────────────────────────────────────────────────────

@admin_bp.route("/records")
@admin_or_faculty_required
def records():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT name, date, time, status, id, COALESCE(late_minutes, 0)
        FROM attendance ORDER BY date DESC, time DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return render_template("attendance.html", records=rows)


@admin_bp.route("/edit/<int:record_id>")
@admin_or_faculty_required
def edit_record(record_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, date, time, status, COALESCE(late_minutes, 0) FROM attendance WHERE id=%s",
        (record_id,),
    )
    record = cur.fetchone()
    conn.close()
    return render_template("edit_attendance.html", record=record)


@admin_bp.route("/update", methods=["POST"])
@admin_or_faculty_required
def update_record():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE attendance SET date=%s, time=%s, status=%s, late_minutes=%s WHERE id=%s",
        (
            request.form["date"],
            request.form["time"],
            request.form["status"],
            int(request.form.get("late_minutes", 0)),
            request.form["id"],
        ),
    )
    conn.commit()
    conn.close()
    return redirect("/records")


@admin_bp.route("/delete/<int:record_id>", methods=["POST"])
@admin_or_faculty_required
def delete_record(record_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM attendance WHERE id=%s", (record_id,))
    conn.commit()
    conn.close()
    return redirect("/records")


@admin_bp.route("/delete/all", methods=["POST"])
@admin_or_faculty_required
def delete_all_records():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM attendance")
    conn.commit()
    conn.close()
    return redirect("/records")


@admin_bp.route("/download/attendance")
@admin_or_faculty_required
def download_attendance():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT name, date, time, status, COALESCE(late_minutes, 0)
        FROM attendance ORDER BY date DESC, time DESC
    """)
    rows = cur.fetchall()
    conn.close()

    output = io.StringIO()
    output.write("Name,Date,Time,Status,Late Minutes\n")
    for row in rows:
        output.write(f"{row[0]},{row[1]},{row[2]},{row[3]},{row[4]}\n")

    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=attendance.csv"
    response.headers["Content-Type"] = "text/csv"
    return response
