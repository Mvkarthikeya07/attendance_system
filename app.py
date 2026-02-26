import os
from dotenv import load_dotenv

from flask import Flask, render_template, request, redirect, session, jsonify, Response
from mysql_db import get_connection
import camera
import auth_db
import base64
import numpy as np
import cv2
from datetime import datetime

load_dotenv()

app = Flask(__name__)
# app.secret_key = "attendance_system_secret_key_2024"
app.secret_key = os.environ.get("SECRET_KEY", "dev_fallback_key")

# =========================================================
# INIT DATABASE (MySQL)
# =========================================================

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance(
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100),
            date VARCHAR(20),
            time VARCHAR(20),
            status VARCHAR(20),
            late_minutes INT DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

init_db()


# =========================================================
# BASIC ROUTES
# =========================================================

@app.route("/")
def index():
    if "user" in session:
        return redirect("/menu")
    return render_template("index.html")


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "")
    password = request.form.get("password", "")

    if username == "admin" and password == "admin":
        session["user"] = username
        return jsonify({"success": True})

    return jsonify({"success": False})


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    return redirect("/")


@app.route("/menu")
def menu():
    if "user" not in session:
        return redirect("/")
    return render_template("menu.html")


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():
    if (
        "user" not in session and
        "faculty_user" not in session and
        "student_user" not in session
    ):
        return redirect("/")

    return render_template("dashboard.html")


# =========================================================
# FRONTEND FRAME UPLOAD
# =========================================================

@app.route("/upload_frame", methods=["POST"])
def upload_frame():
    data = request.json
    image_data = data.get("image")

    if not image_data:
        return jsonify({"status": "error"}), 400

    image_data = image_data.split(",")[1]
    image_bytes = base64.b64decode(image_data)
    np_arr = np.frombuffer(image_bytes, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    camera.update_frame(frame)

    return jsonify({"status": "ok"})


@app.route("/register", methods=["POST"])
def register():
    camera.STUDENT_NAME = request.form["name"]
    camera.MODE = "register"
    camera.COUNT = 0
    camera.MESSAGE = "Registering..."
    return ("", 204)


# =========================================================
# START ATTENDANCE
# =========================================================

@app.route("/start_attendance")
def start_attendance():
    from datetime import date as date_cls

    camera.MODE = "attendance"
    camera.ATTENDANCE_START_TIME = datetime.now()

    try:
        today = date_cls.today().isoformat()
        status = auth_db.get_session_status(today)
        if status["has_session"]:
            if status["mode"] == "late":
                camera.ATTENDANCE_TYPE = "late"
                end_time_str = status["end_time"]
                today_date = date_cls.today()
                end_h, end_m = map(int, end_time_str.split(":"))
                camera.SESSION_END_TIME = datetime(
                    today_date.year, today_date.month, today_date.day,
                    end_h, end_m
                )
            elif status["mode"] == "normal":
                camera.ATTENDANCE_TYPE = "normal"
                camera.SESSION_END_TIME = None
    except Exception:
        pass

    camera.MESSAGE = "Taking Attendance..."
    return ("", 204)


# =========================================================
# STOP ATTENDANCE
# =========================================================

@app.route("/stop_attendance")
def stop_attendance():

    camera.MODE = "idle"
    camera.mark_absent_remaining(camera.ATTENDANCE_TYPE)
    camera.SESSION_END_TIME = None
    camera.ATTENDANCE_TYPE = "normal"

    camera.MESSAGE = "Attendance Ended"
    return ("", 204)


# =========================================================
# VIDEO STREAM
# =========================================================

@app.route("/video_feed")
def video_feed():
    return Response(
        camera.gen_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


# =========================================================
# RECORDS
# =========================================================

@app.route("/records")
def records():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT name, date, time, status, id, COALESCE(late_minutes, 0)
        FROM attendance
        ORDER BY date DESC, time DESC
    """)

    rows = cur.fetchall()
    conn.close()

    return render_template("attendance.html", records=rows)


@app.route("/delete/all", methods=["POST"])
def delete_all_records():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM attendance")
    conn.commit()
    conn.close()
    return redirect("/records")


@app.route("/edit/<int:record_id>")
def edit_record(record_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, date, time, status, COALESCE(late_minutes, 0) FROM attendance WHERE id=%s",
        (record_id,)
    )
    record = cur.fetchone()
    conn.close()
    return render_template("edit_attendance.html", record=record)


@app.route("/update", methods=["POST"])
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
            request.form["id"]
        )
    )
    conn.commit()
    conn.close()
    return redirect("/records")


@app.route("/delete/<int:record_id>", methods=["POST"])
def delete_record(record_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM attendance WHERE id=%s", (record_id,))
    conn.commit()
    conn.close()
    return redirect("/records")


@app.route("/download/attendance")
def download_attendance():
    import io
    from flask import make_response

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT name, date, time, status, COALESCE(late_minutes, 0)
        FROM attendance
        ORDER BY date DESC, time DESC
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


# =========================================================
# BLUEPRINT
# =========================================================

from app_extension import ext_bp
app.register_blueprint(ext_bp)


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    app.run()