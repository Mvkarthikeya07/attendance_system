"""
Attendance routes — camera dashboard, frame processing, controls.
"""

from functools import wraps
from datetime import datetime, date as date_cls

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


# ── Frame processing ───────────────────────────────────────────────
# Browser sends a JPEG frame via POST, server processes it with
# YOLO + LBPH and returns the annotated JPEG + status message.

@attendance_bp.route("/api/frame", methods=["POST"])
@login_required
def api_frame():
    # Accept both multipart (FormData) and raw octet-stream
    if request.content_type and "multipart" in request.content_type:
        file = request.files.get("frame")
        if not file:
            return jsonify({"error": "No frame data"}), 400
        jpeg_bytes = file.read()
    else:
        jpeg_bytes = request.data

    if not jpeg_bytes:
        return jsonify({"error": "No frame data"}), 400

    annotated, message = camera.process_frame(jpeg_bytes)
    if annotated is None:
        return jsonify({"error": message}), 400

    return Response(
        annotated,
        mimetype="image/jpeg",
        headers={"X-Message": message},
    )


# ── Status endpoint (polled by JS for mode/message updates) ────────

@attendance_bp.route("/api/status")
@login_required
def api_status():
    return jsonify({
        "mode": camera.MODE,
        "message": camera.MESSAGE,
        "count": camera.COUNT,
        "student_name": camera.STUDENT_NAME,
    })


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
