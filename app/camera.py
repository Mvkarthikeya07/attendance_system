"""
Face detection, recognition, registration, and attendance marking.

Architecture (cloud-compatible):
  - The browser captures webcam frames via getUserMedia + canvas.
  - JavaScript POSTs each frame (JPEG blob) to /api/frame.
  - This module processes the frame (YOLO detection + LBPH recognition)
    and returns an annotated JPEG + status message.
  - There is NO server-side VideoCapture — cloud servers have no camera.
"""

import os
import time
import pickle
import threading

_register_lock = threading.Lock()

# Set Ultralytics config dir before importing YOLO
# (avoids warning on read-only filesystems like Render)
# Ultralytics appends its own 'Ultralytics' subfolder, so point to /tmp
if not os.environ.get("YOLO_CONFIG_DIR"):
    os.environ["YOLO_CONFIG_DIR"] = "/tmp"

import cv2
import numpy as np
from collections import Counter, defaultdict
from datetime import date, datetime
from ultralytics import YOLO

from app.config import MODEL_PATH
from app.database import get_connection

# Ensure dataset directory exists
os.makedirs("dataset", exist_ok=True)

# ── System state ────────────────────────────────────────────────────
MODE = "idle"
STUDENT_NAME = ""
COUNT = 0
MESSAGE = ""
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

# The model file yolov8s-face-lindevs.pt is bundled in the repo.
# If it's missing for any reason, fall back to generic yolov8n.
if not os.path.isfile(_model_path):
    print(f"WARNING: Face model '{_model_path}' not found. Falling back to yolov8n.pt")
    _model_path = "yolov8n.pt"

yolo_model = YOLO(_model_path)


# ── Training ────────────────────────────────────────────────────────

def train_model():
    global recognizer, label_map, MESSAGE, MODE

    if not _has_lbph:
        MESSAGE = "Face recognition module unavailable"
        MODE = "idle"
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
        MESSAGE = "No face images found"
        MODE = "idle"
        return

    new_recognizer = cv2.face.LBPHFaceRecognizer_create()
    new_recognizer.train(faces, np.array(labels))
    new_recognizer.save(TRAINER_PATH)

    with open(LABELS_PATH, "wb") as f:
        pickle.dump(new_label_map, f)

    recognizer = new_recognizer
    label_map = new_label_map
    print(f"Model retrained. Labels: {label_map}")

    MESSAGE = f"Registered: {STUDENT_NAME}"
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


# ── Process a single frame from the browser ─────────────────────────

def process_frame(jpeg_bytes):
    """
    Receive raw JPEG bytes (from the browser webcam), run YOLO face
    detection + LBPH recognition, and return (annotated_jpeg_bytes, message).

    Runs YOLO face detection + LBPH recognition on the frame and returns
    the annotated JPEG bytes and a status message string.
    """
    global COUNT, MESSAGE, recent_predictions, ATTENDANCE_START_TIME

    # Decode JPEG into OpenCV image
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return None, "Invalid frame"

    if MODE == "attendance" and ATTENDANCE_START_TIME is None:
        ATTENDANCE_START_TIME = datetime.now()
    if MODE != "attendance":
        ATTENDANCE_START_TIME = None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    results = yolo_model(frame, conf=0.5, imgsz=320, verbose=False)
    active_faces = set()

    if len(results[0].boxes) == 0:
        if MODE == "attendance":
            MESSAGE = "No face detected"
        elif MODE == "register":
            MESSAGE = "Look at the camera"
        recent_predictions.clear()

    for box in results[0].boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        if (x2 - x1) < 60 or (y2 - y1) < 60:
            continue

        face = gray[y1:y2, x1:x2]
        if face.size == 0:
            continue

        face_id = f"{x1 // 50}_{y1 // 50}"
        active_faces.add(face_id)
        display_name = ""

        # Registration mode (locked to prevent race conditions)
        if MODE == "register":
            with _register_lock:
                if COUNT < 10:
                    os.makedirs(os.path.join(DATASET_DIR, STUDENT_NAME), exist_ok=True)
                    COUNT += 1
                    face_save = cv2.resize(face, (200, 200))
                    cv2.imwrite(
                        os.path.join(DATASET_DIR, STUDENT_NAME, f"{COUNT}.jpg"), face_save
                    )
                    MESSAGE = f"Capturing {COUNT}/10"
                elif COUNT == 10:
                    MESSAGE = "Training..."
                    threading.Thread(target=train_model, daemon=True).start()
                    COUNT = 11

        # Attendance mode
        if MODE == "attendance":
            if not recognizer:
                MESSAGE = "No trained model"
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
                        MESSAGE = f"{display_name} — Present"
                    else:
                        display_name = "Verifying..."
                        MESSAGE = "Recognizing..."
                else:
                    display_name = "Unknown"
                    MESSAGE = "Unknown face"

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
    return buffer.tobytes(), MESSAGE
