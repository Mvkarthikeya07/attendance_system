import cv2
import os
import time
import pickle
from mysql_db import get_connection
import threading
import numpy as np
import requests as req
from datetime import date, datetime
from collections import Counter, defaultdict
from ultralytics import YOLO

# Ensure dataset directory exists (it's gitignored, won't exist on fresh deploy)
os.makedirs("dataset", exist_ok=True)

# =========================================================
# FRONTEND FRAME BUFFER (REPLACES VideoCapture)
# =========================================================
latest_frame = None

def update_frame(frame):
    global latest_frame
    latest_frame = frame


# ---------------- SYSTEM STATE ----------------
MODE = "idle"
STUDENT_NAME = ""
COUNT = 0
MESSAGE = "Waiting..."
ATTENDANCE_TYPE = "normal"
ATTENDANCE_START_TIME = None
SESSION_END_TIME = None

recent_predictions = defaultdict(list)

recognizer = None
label_map = {}

if os.path.exists("trainer.yml") and os.path.exists("labels.pickle"):
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read("trainer.yml")
    with open("labels.pickle", "rb") as f:
        label_map = pickle.load(f)

MODEL_PATH = os.environ.get("MODEL_PATH", "yolov8s-face-lindevs.pt")
MODEL_URL = "https://github.com/lindevs/yolov8-face/releases/download/v1.0.0/yolov8s-face-lindevs.pt"

if not os.path.isfile(MODEL_PATH):
    print(f"Downloading YOLO model from {MODEL_URL}...")
    response = req.get(MODEL_URL, stream=True)
    response.raise_for_status()
    with open(MODEL_PATH, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    print("Model downloaded successfully.")

yolo_model = YOLO(MODEL_PATH)


# =========================================================
# AUTO TRAIN MODEL AFTER REGISTRATION
# =========================================================

def train_model():
    global recognizer, label_map

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATASET = os.path.join(BASE_DIR, "dataset")
    TRAINER_PATH = os.path.join(BASE_DIR, "trainer.yml")
    LABELS_PATH = os.path.join(BASE_DIR, "labels.pickle")

    faces, labels, label_map_new = [], [], {}
    label_id = 0

    for name in sorted(os.listdir(DATASET)):
        person_dir = os.path.join(DATASET, name)
        if not os.path.isdir(person_dir):
            continue
        label_map_new[label_id] = name
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
        print("❌ No face images found for training")
        return

    new_recognizer = cv2.face.LBPHFaceRecognizer_create()
    new_recognizer.train(faces, np.array(labels))
    new_recognizer.save(TRAINER_PATH)

    with open(LABELS_PATH, "wb") as f:
        pickle.dump(label_map_new, f)

    recognizer = new_recognizer
    label_map = label_map_new
    print(f"✅ Model retrained automatically. Labels: {label_map}")


# =========================================================
# DATABASE FUNCTIONS (UNCHANGED)
# =========================================================

def calculate_late_minutes(now):
    global ATTENDANCE_START_TIME, SESSION_END_TIME

    if SESSION_END_TIME is not None:
        diff = now - SESSION_END_TIME
        return max(0, int(diff.total_seconds() // 60))

    if ATTENDANCE_START_TIME is None:
        return 0

    diff = now - ATTENDANCE_START_TIME
    return max(0, int(diff.total_seconds() // 60))


def mark_present_once(name):
    global ATTENDANCE_TYPE

    today = date.today().isoformat()
    now = datetime.now()
    now_time = now.strftime("%H:%M:%S")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT status FROM attendance
        WHERE name=%s AND date=%s
    """, (name, today))

    row = cur.fetchone()

    if row is None:
        status = "PRESENT"
        late_minutes = 0

        if ATTENDANCE_TYPE == "late":
            late_minutes = calculate_late_minutes(now)
            status = "LATE"

        cur.execute("""
            INSERT INTO attendance (name, date, time, status, late_minutes)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, today, now_time, status, late_minutes))

        conn.commit()
        conn.close()
        return

    existing_status = row[0]

    if existing_status == "ABSENT":
        status = "PRESENT"
        late_minutes = 0

        if ATTENDANCE_TYPE == "late":
            late_minutes = calculate_late_minutes(now)
            status = "LATE"

        cur.execute("""
            UPDATE attendance
            SET time=%s, status=%s, late_minutes=%s
            WHERE name=%s AND date=%s
        """, (now_time, status, late_minutes, name, today))

        conn.commit()

    conn.close()


def mark_absent_remaining(attendance_type="normal"):
    today = date.today().isoformat()
    now_time = datetime.now().strftime("%H:%M:%S")

    registered = [
        d for d in os.listdir("dataset")
        if os.path.isdir(os.path.join("dataset", d))
    ]

    conn = get_connection()
    cur = conn.cursor()

    for person in registered:
        cur.execute("""
            SELECT 1 FROM attendance
            WHERE name=%s AND date=%s
        """, (person, today))

        if cur.fetchone() is None:
            cur.execute("""
                INSERT INTO attendance (name, date, time, status, late_minutes)
                VALUES (%s, %s, %s, %s, %s)
            """, (person, today, now_time, "ABSENT", 0))

    conn.commit()
    conn.close()


# =========================================================
# SAME gen_frames() — ONLY CAMERA SOURCE CHANGED
# =========================================================

def gen_frames():
    global COUNT, MESSAGE, recent_predictions, ATTENDANCE_START_TIME, latest_frame
    last_capture_time = 0

    while True:

        if latest_frame is None:
            time.sleep(0.1)
            continue

        frame = latest_frame.copy()

        # Same logic as before
        if MODE == "attendance" and ATTENDANCE_START_TIME is None:
            ATTENDANCE_START_TIME = datetime.now()

        if MODE != "attendance":
            ATTENDANCE_START_TIME = None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        results = yolo_model(frame, conf=0.5, imgsz=480)

        active_faces = set()

        if len(results[0].boxes) == 0:
            MESSAGE = "No person detected"
            recent_predictions.clear()

        for box in results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            if (x2 - x1) < 80 or (y2 - y1) < 80:
                continue

            face = gray[y1:y2, x1:x2]
            if face.size == 0:
                continue

            face_id = f"{x1//50}_{y1//50}"
            active_faces.add(face_id)

            display_name = ""

            if MODE == "register":
                if COUNT < 10:
                    os.makedirs(f"dataset/{STUDENT_NAME}", exist_ok=True)
                    COUNT += 1
                    cv2.imwrite(f"dataset/{STUDENT_NAME}/{COUNT}.jpg", face)
                    MESSAGE = f"Registering {STUDENT_NAME}: {COUNT}/10"
                elif COUNT == 10:
                    MESSAGE = f"Training model for {STUDENT_NAME}..."
                    threading.Thread(target=train_model, daemon=True).start()
                    COUNT = 11  # prevent re-triggering

            if MODE == "attendance" and recognizer:
                label, conf = recognizer.predict(face)

                if conf <= 80 and label in label_map:
                    recent_predictions[face_id].append(label_map[label])

                    if len(recent_predictions[face_id]) > 10:
                        recent_predictions[face_id].pop(0)

                    common = Counter(
                        recent_predictions[face_id]
                    ).most_common(1)

                    if common and common[0][1] >= 7:
                        display_name = common[0][0]
                        mark_present_once(display_name)
                    else:
                        display_name = "Verifying..."
                else:
                    display_name = "Unknown"

            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            if display_name:
                cv2.putText(
                    frame,
                    display_name,
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2
                )

        for fid in list(recent_predictions.keys()):
            if fid not in active_faces:
                del recent_predictions[fid]

        cv2.putText(
            frame,
            MESSAGE,
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 255, 0),
            2
        )

        _, buffer = cv2.imencode(".jpg", frame)
        frame = buffer.tobytes()

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        )
