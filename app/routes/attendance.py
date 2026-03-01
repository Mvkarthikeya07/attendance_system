"""
Attendance routes — camera dashboard, frame upload, video feed.
"""

from functools import wraps
from datetime import datetime, date as date_cls

import base64
import numpy as np
import cv2
from flask import Blueprint, render_template, request, redirect, session, jsonify, Response

from app import auth, camera

attendance_bp = Blueprint("attendance", __name__)


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not any(k in session for k in ("user", "faculty_user", "student_user")):
            return redirect("/")
        return f(*args, **kwargs)
    return wrapper


def admin_or_faculty_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session and "faculty_user" not in session:
            return redirect("/")
        return f(*args, **kwargs)
    return wrapper


# ── Dashboard ───────────────────────────────────────────────────────

@attendance_bp.route("/dashboard")
@login_required
def dashboard():
    attendance_type = request.args.get("attendance_type", "normal")
    return render_template("dashboard.html", attendance_type=attendance_type)


# ── Frame upload (JSON base64) ──────────────────────────────────────

@attendance_bp.route("/upload_frame", methods=["POST"])
@login_required
def upload_frame():
    data = request.json
    image_data = data.get("image") if data else None
    if not image_data:
        return jsonify({"status": "error"}), 400

    image_data = image_data.split(",")[1]
    image_bytes = base64.b64decode(image_data)
    np_arr = np.frombuffer(image_bytes, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    camera.update_frame(frame)
    return jsonify({"status": "ok"})


# ── Frame upload (multipart) ───────────────────────────────────────

@attendance_bp.route("/process_frame", methods=["POST"])
@login_required
def process_frame():
    file = request.files.get("frame")
    if not file:
        return jsonify({"status": "error"}), 400
    np_arr = np.frombuffer(file.read(), np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if frame is not None:
        camera.update_frame(frame)
    return jsonify({"status": "ok"})


# ── Register face ──────────────────────────────────────────────────

@attendance_bp.route("/register", methods=["POST"])
@login_required
def register():
    camera.STUDENT_NAME = request.form["name"]
    camera.MODE = "register"
    camera.COUNT = 0
    camera.MESSAGE = "Registering..."
    return ("", 204)


# ── Start / Stop attendance ─────────────────────────────────────────

@attendance_bp.route("/start_attendance")
@admin_or_faculty_required
def start_attendance():
    camera.MODE = "attendance"
    camera.ATTENDANCE_START_TIME = datetime.now()

    try:
        today = date_cls.today().isoformat()
        status = auth.get_session_status(today)
        if status["has_session"]:
            if status["mode"] == "late":
                camera.ATTENDANCE_TYPE = "late"
                end_h, end_m = map(int, status["end_time"].split(":"))
                td = date_cls.today()
                camera.SESSION_END_TIME = datetime(td.year, td.month, td.day, end_h, end_m)
            elif status["mode"] == "normal":
                camera.ATTENDANCE_TYPE = "normal"
                camera.SESSION_END_TIME = None
    except Exception:
        pass

    camera.MESSAGE = "Taking Attendance..."
    return ("", 204)


@attendance_bp.route("/stop_attendance")
@admin_or_faculty_required
def stop_attendance():
    camera.MODE = "idle"
    camera.mark_absent_remaining(camera.ATTENDANCE_TYPE)
    camera.SESSION_END_TIME = None
    camera.ATTENDANCE_TYPE = "normal"
    camera.MESSAGE = "Attendance Ended"
    return ("", 204)


# ── Video feed (MJPEG) ─────────────────────────────────────────────

@attendance_bp.route("/video_feed")
@login_required
def video_feed():
    return Response(
        camera.gen_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )
