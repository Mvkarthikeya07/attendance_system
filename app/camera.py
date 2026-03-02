"""
Face detection, recognition, registration, and attendance marking.
"""

import os
import time
import pickle
import threading

import cv2
import numpy as np
import requests as req
from collections import Counter, defaultdict
from datetime import date, datetime
from ultralytics import YOLO

from app.config import MODEL_PATH
from app.database import get_connection

# Ensure dataset directory exists
os.makedirs("dataset", exist_ok=True)

# ── Frame buffer (replaces VideoCapture) ────────────────────────────
latest_frame = None


def update_frame(frame):
    global latest_frame
    latest_frame = frame


# ── System state ────────────────────────────────────────────────────
MODE = "idle"
STUDENT_NAME = ""
COUNT = 0
MESSAGE = "Attendence Closed"
ATTENDANCE_TYPE = "normal"
ATTENDANCE_START_TIME = None
SESSION_END_TIME = None

recent_predictions: dict = defaultdict(list)

# ── Load existing recogniser if available ───────────────────────────
recognizer = None
label_map: dict = {}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAINER_PATH = os.path.join(BASE_DIR, "trainer.yml")
LABELS_PATH = os.path.join(BASE_DIR, "labels.pickle")
DATASET_DIR = os.path.join(BASE_DIR, "dataset")

try:
    _has_lbph = hasattr(cv2, "face") and hasattr(cv2.face, "LBPHFaceRecognizer_create")
except Exception:
    _has_lbph = False

if _has_lbph and os.path.exists(TRAINER_PATH) and os.path.exists(LABELS_PATH):
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(TRAINER_PATH)
    with open(LABELS_PATH, "rb") as f:
        label_map = pickle.load(f)
elif not _has_lbph:
    print("WARNING: cv2.face.LBPHFaceRecognizer not available. "
          "Install opencv-contrib-python (same version as opencv-python) to enable face recognition.")

# ── YOLO model download / load ──────────────────────────────────────
_model_path = MODEL_PATH
MODEL_URLS = [
    "https://github.com/akanametov/yolov8-face/releases/download/v0.0.0/yolov8n-face.pt",
    "https://github.com/derronqi/yolov8-face/releases/download/v1/yolov8n-face.pt",
]

if not os.path.isfile(_model_path):
    downloaded = False
    for url in MODEL_URLS:
        try:
            print(f"Downloading YOLO model from {url} ...")
            response = req.get(url, stream=True, timeout=30)
            response.raise_for_status()
            with open(_model_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print("Model downloaded successfully.")
            downloaded = True
            break
        except Exception as e:
            print(f"Failed: {e}")
    if not downloaded:
        print("All face-model URLs failed. Falling back to yolov8n.pt")
        _model_path = "yolov8n.pt"

yolo_model = YOLO(_model_path)


# ── Training ────────────────────────────────────────────────────────

def train_model():
    global recognizer, label_map, MESSAGE, MODE

    if not _has_lbph:
        MESSAGE = "ERROR: Face recognition module not available"
        MODE = "idle"
        print("ERROR: Cannot train — cv2.face.LBPHFaceRecognizer not available.")
        return

    faces, labels, new_label_map = [], [], {}
    label_id = 0

    for name in sorted(os.listdir(DATASET_DIR)):
        person_dir = os.path.join(DATASET_DIR, name)
        if not os.path.isdir(person_dir):
            continue
        new_label_map[label_id] = name
        for img_file in os.listdir(person_dir):
            if not img_file.lower().endswith(".jpg"):
                continue
            image = cv2.imread(os.path.join(person_dir, img_file), cv2.IMREAD_GRAYSCALE)
            if image is None:
                continue
            image = cv2.resize(image, (200, 200))
            faces.append(image)
            labels.append(label_id)
        label_id += 1

    if not faces:
        MESSAGE = "No face images found for training"
        MODE = "idle"
        print("No face images found for training.")
        return

    new_recognizer = cv2.face.LBPHFaceRecognizer_create()
    new_recognizer.train(faces, np.array(labels))
    new_recognizer.save(TRAINER_PATH)

    with open(LABELS_PATH, "wb") as f:
        pickle.dump(new_label_map, f)

    recognizer = new_recognizer
    label_map = new_label_map
    print(f"Model retrained. Labels: {label_map}")

    # Update UI state so dashboard shows completion
    MESSAGE = f"Registration Complete for {STUDENT_NAME}!"
    # Keep MODE as register for a moment so dashboard can read it, then go idle
    time.sleep(2)
    MODE = "idle"


# ── Attendance helpers ──────────────────────────────────────────────

def calculate_late_minutes(now):
    if SESSION_END_TIME is not None:
        diff = now - SESSION_END_TIME
        return max(0, int(diff.total_seconds() // 60))
    if ATTENDANCE_START_TIME is None:
        return 0
    diff = now - ATTENDANCE_START_TIME
    return max(0, int(diff.total_seconds() // 60))


def mark_present_once(name):
    today = date.today().isoformat()
    now = datetime.now()
    now_time = now.strftime("%H:%M:%S")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT status FROM attendance WHERE name=%s AND date=%s", (name, today))
    row = cur.fetchone()

    if row is None:
        status = "LATE" if ATTENDANCE_TYPE == "late" else "PRESENT"
        late_min = calculate_late_minutes(now) if ATTENDANCE_TYPE == "late" else 0
        cur.execute(
            "INSERT INTO attendance (name, date, time, status, late_minutes) VALUES (%s,%s,%s,%s,%s)",
            (name, today, now_time, status, late_min),
        )
        conn.commit()
        conn.close()
        return

    if row[0] == "ABSENT":
        status = "LATE" if ATTENDANCE_TYPE == "late" else "PRESENT"
        late_min = calculate_late_minutes(now) if ATTENDANCE_TYPE == "late" else 0
        cur.execute(
            "UPDATE attendance SET time=%s, status=%s, late_minutes=%s WHERE name=%s AND date=%s",
            (now_time, status, late_min, name, today),
        )
        conn.commit()

    conn.close()


def mark_absent_remaining(attendance_type="normal"):
    today = date.today().isoformat()
    now_time = datetime.now().strftime("%H:%M:%S")

    registered = [
        d for d in os.listdir(DATASET_DIR)
        if os.path.isdir(os.path.join(DATASET_DIR, d))
    ]

    conn = get_connection()
    cur = conn.cursor()
    for person in registered:
        cur.execute("SELECT 1 FROM attendance WHERE name=%s AND date=%s", (person, today))
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO attendance (name, date, time, status, late_minutes) VALUES (%s,%s,%s,%s,%s)",
                (person, today, now_time, "ABSENT", 0),
            )
    conn.commit()
    conn.close()


# ── Frame generator (MJPEG stream) ─────────────────────────────────

def gen_frames():
    global COUNT, MESSAGE, recent_predictions, ATTENDANCE_START_TIME, latest_frame

    while True:
        if latest_frame is None:
            time.sleep(0.1)
            continue

        frame = latest_frame.copy()

        if MODE == "attendance" and ATTENDANCE_START_TIME is None:
            ATTENDANCE_START_TIME = datetime.now()
        if MODE != "attendance":
            ATTENDANCE_START_TIME = None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        results = yolo_model(frame, conf=0.5, imgsz=320, verbose=False)
        active_faces = set()

        if len(results[0].boxes) == 0:
            if MODE == "attendance":
                MESSAGE = "Taking Attendance... No face detected"
            elif MODE == "register":
                MESSAGE = "Waiting for face — look at the camera"
            else:
                MESSAGE = "Waiting..."
            recent_predictions.clear()

        for box in results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            if (x2 - x1) < 80 or (y2 - y1) < 80:
                continue

            face = gray[y1:y2, x1:x2]
            if face.size == 0:
                continue

            face_id = f"{x1 // 50}_{y1 // 50}"
            active_faces.add(face_id)
            display_name = ""

            # Registration mode
            if MODE == "register":
                if COUNT < 10:
                    os.makedirs(os.path.join(DATASET_DIR, STUDENT_NAME), exist_ok=True)
                    COUNT += 1
                    face_save = cv2.resize(face, (200, 200))
                    cv2.imwrite(
                        os.path.join(DATASET_DIR, STUDENT_NAME, f"{COUNT}.jpg"), face_save
                    )
                    MESSAGE = f"Capturing {STUDENT_NAME}: {COUNT}/10 — Hold still"
                elif COUNT == 10:
                    MESSAGE = f"Training model for {STUDENT_NAME}... Please wait"
                    threading.Thread(target=train_model, daemon=True).start()
                    COUNT = 11
                # COUNT > 10 means training in progress or done — MESSAGE is set by train_model()

            # Attendance mode
            if MODE == "attendance":
                if not recognizer:
                    MESSAGE = "No trained model — register faces first"
                else:
                    face_resized = cv2.resize(face, (200, 200))
                    label, conf = recognizer.predict(face_resized)
                    if conf <= 80 and label in label_map:
                        recent_predictions[face_id].append(label_map[label])
                        if len(recent_predictions[face_id]) > 10:
                            recent_predictions[face_id].pop(0)
                        common = Counter(recent_predictions[face_id]).most_common(1)
                        if common and common[0][1] >= 7:
                            display_name = common[0][0]
                            mark_present_once(display_name)
                            MESSAGE = f"Marked: {display_name} Present"
                        else:
                            display_name = "Verifying..."
                            MESSAGE = "Recognizing face..."
                    else:
                        display_name = "Unknown"
                        MESSAGE = "Face not recognized"

            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            if display_name:
                cv2.putText(frame, display_name, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        # Remove stale predictions
        for fid in list(recent_predictions.keys()):
            if fid not in active_faces:
                del recent_predictions[fid]

        cv2.putText(frame, MESSAGE, (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
        )

        # Pace the MJPEG stream — ~12 fps is plenty for a live preview
        time.sleep(0.08)
