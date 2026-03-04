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
_marked_today: set = set()   # in-memory cache of students marked today

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
    """Mark student present. Returns True if a new mark was made."""
    global _marked_today
    if name in _marked_today:
        return False

    today = date.today().isoformat()
    now = datetime.now()
    now_time = now.strftime("%H:%M:%S")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT status FROM attendance WHERE name=%s AND date=%s", (name, today))
    row = cur.fetchone()

    marked = False
    if row is None:
        status = "LATE" if ATTENDANCE_TYPE == "late" else "PRESENT"
        late_min = calculate_late_minutes(now) if ATTENDANCE_TYPE == "late" else 0
        cur.execute(
            "INSERT INTO attendance (name, date, time, status, late_minutes) VALUES (%s,%s,%s,%s,%s)",
            (name, today, now_time, status, late_min),
        )
        conn.commit()
        marked = True
    elif row[0] == "ABSENT":
        status = "LATE" if ATTENDANCE_TYPE == "late" else "PRESENT"
        late_min = calculate_late_minutes(now) if ATTENDANCE_TYPE == "late" else 0
        cur.execute(
            "UPDATE attendance SET time=%s, status=%s, late_minutes=%s WHERE name=%s AND date=%s",
            (now_time, status, late_min, name, today),
        )
        conn.commit()
        marked = True
    conn.close()

    if marked or row is not None:
        _marked_today.add(name)
    return marked


def _check_all_marked():
    """Return True if every registered student has been marked present/late today."""
    today = date.today().isoformat()
    registered = [d for d in os.listdir(DATASET_DIR)
                  if os.path.isdir(os.path.join(DATASET_DIR, d))]
    if not registered:
        return False
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(DISTINCT name) FROM attendance WHERE date=%s AND status IN ('PRESENT','LATE')",
        (today,)
    )
    marked = cur.fetchone()[0]
    conn.close()
    return marked >= len(registered)


def _auto_stop_attendance():
    """Background thread: mark absent + auto-stop if all marked."""
    global MODE, SESSION_END_TIME, ATTENDANCE_TYPE, MESSAGE
    try:
        if _check_all_marked():
            mark_absent_remaining(ATTENDANCE_TYPE)
            SESSION_END_TIME = None
            ATTENDANCE_TYPE = "normal"
            MODE = "idle"
            MESSAGE = ""
    except Exception:
        pass


def _bg_mark_and_check(name):
    """Background thread: write DB mark then check if all done."""
    try:
        mark_present_once(name)
        _auto_stop_attendance()
    except Exception:
        pass


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
    Receive raw JPEG bytes from the browser webcam, run YOLO face
    detection + LBPH recognition.

    Returns (faces_list, message) where faces_list is a list of dicts:
      [{"x1": int, "y1": int, "x2": int, "y2": int, "name": str}, ...]
    """
    global COUNT, MESSAGE, recent_predictions, ATTENDANCE_START_TIME, MODE, SESSION_END_TIME, ATTENDANCE_TYPE

    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return None, "Invalid frame"

    h_frame, w_frame = frame.shape[:2]

    if MODE == "attendance" and ATTENDANCE_START_TIME is None:
        ATTENDANCE_START_TIME = datetime.now()
    if MODE != "attendance":
        ATTENDANCE_START_TIME = None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    results = yolo_model(frame, conf=0.45, imgsz=320, verbose=False)
    active_faces = set()
    faces_out = []

    # Collect detected face boxes first
    detected_boxes = []
    for box in results[0].boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        if (x2 - x1) < 60 or (y2 - y1) < 60:
            continue
        face = gray[y1:y2, x1:x2]
        if face.size == 0:
            continue
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        detected_boxes.append((x1, y1, x2, y2, cx, cy, face))

    if not detected_boxes:
        if MODE == "attendance":
            MESSAGE = "No face detected"
        elif MODE == "register":
            MESSAGE = "Look at the camera"
        recent_predictions.clear()

    # Match each detection to nearest existing tracked face or create new track
    _used_ids = set()
    for (x1, y1, x2, y2, cx, cy, face) in detected_boxes:
        # Find closest existing tracked face
        best_id = None
        best_dist = 9999
        for fid in recent_predictions:
            if fid in _used_ids:
                continue
            parts = fid.split("_")
            fx, fy = int(parts[0]), int(parts[1])
            dist = abs(cx - fx) + abs(cy - fy)
            if dist < best_dist:
                best_dist = dist
                best_id = fid
        # If close enough, reuse; otherwise create new
        if best_id and best_dist < 120:
            face_id = best_id
        else:
            face_id = f"{cx}_{cy}"
        # Update face_id center to current position
        new_id = f"{cx}_{cy}"
        if face_id != new_id and face_id in recent_predictions:
            recent_predictions[new_id] = recent_predictions.pop(face_id)
            face_id = new_id

        active_faces.add(face_id)
        _used_ids.add(face_id)
        display_name = ""

        # Registration mode
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
            display_name = STUDENT_NAME if COUNT <= 11 else ""

        # Attendance mode
        if MODE == "attendance":
            if not recognizer:
                MESSAGE = "No trained model"
            else:
                face_resized = cv2.resize(face, (200, 200))
                label, conf = recognizer.predict(face_resized)
                if conf <= 80 and label in label_map:
                    pred_name = label_map[label]
                else:
                    pred_name = "_unknown_"

                recent_predictions[face_id].append(pred_name)
                preds = recent_predictions[face_id]
                if len(preds) > 7:
                    recent_predictions[face_id] = preds[-7:]
                    preds = recent_predictions[face_id]

                common = Counter(preds).most_common(1)
                if len(preds) >= 5 and common[0][1] >= 7:
                    top_name = common[0][0]
                    if top_name == "_unknown_":
                        display_name = "Unknown"
                    else:
                        display_name = top_name
                        if display_name in _marked_today:
                            MESSAGE = f"{display_name} — Already marked"
                        else:
                            _marked_today.add(display_name)
                            MESSAGE = f"{display_name} — Present"
                            recent_predictions[face_id] = []
                            threading.Thread(
                                target=_bg_mark_and_check,
                                args=(display_name,),
                                daemon=True
                            ).start()
                else:
                    display_name = "Verifying..."

        # Normalise box coords to 0-1 range so client can scale to its video size
        faces_out.append({
            "x1": round(x1 / w_frame, 4),
            "y1": round(y1 / h_frame, 4),
            "x2": round(x2 / w_frame, 4),
            "y2": round(y2 / h_frame, 4),
            "name": display_name,
        })

    # Remove stale predictions
    for fid in list(recent_predictions.keys()):
        if fid not in active_faces:
            del recent_predictions[fid]

    return faces_out, MESSAGE
