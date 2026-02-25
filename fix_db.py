import sqlite3

conn = sqlite3.connect("database/attendance.db")
cur = conn.cursor()

cur.execute("ALTER TABLE attendance ADD COLUMN status TEXT")

conn.commit()
conn.close()

print("✅ status column added successfully")
