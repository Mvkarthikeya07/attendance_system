import cv2
import os
import sqlite3
from datetime import datetime, date

recognizer = cv2.face.LBPHFaceRecognizer_create()
recognizer.read("trainer.yml")

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

students = os.listdir("dataset")
present_students = set()

cam = cv2.VideoCapture(0)
start = datetime.now()

while (datetime.now() - start).seconds < 10:
    ret, frame = cam.read()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    for (x,y,w,h) in faces:
        id_, conf = recognizer.predict(gray[y:y+h, x:x+w])
        if conf < 80:
            present_students.add(students[id_])

        cv2.rectangle(frame,(x,y),(x+w,y+h),(0,255,0),2)

    cv2.imshow("Taking Attendance", frame)
    cv2.waitKey(1)

cam.release()
cv2.destroyAllWindows()

conn = sqlite3.connect("database/attendance.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT,
    date TEXT,
    time TEXT,
    status TEXT
)
""")

today = date.today().isoformat()
time_now = datetime.now().strftime("%H:%M:%S")

for student in students:
    cur.execute("""
    SELECT * FROM attendance
    WHERE student_id=? AND date=?
    """, (student, today))

    if cur.fetchone():
        continue  # already marked today

    status = "PRESENT" if student in present_students else "ABSENT"
    cur.execute("""
    INSERT INTO attendance VALUES (NULL,?,?,?,?)
    """, (student, today, time_now, status))

conn.commit()
conn.close()
