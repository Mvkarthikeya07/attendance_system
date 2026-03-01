import os

# ── Flask ────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", "dev_fallback_key")
PASSWORD_SALT = os.environ.get("PASSWORD_SALT", "dev_salt")

# ── MySQL (Railway-style keys) ───────────────────────────
MYSQLHOST = os.environ.get("MYSQLHOST")
MYSQLUSER = os.environ.get("MYSQLUSER")
MYSQLPASSWORD = os.environ.get("MYSQLPASSWORD")
MYSQLDATABASE = os.environ.get("MYSQLDATABASE")
MYSQLPORT = int(os.environ.get("MYSQLPORT", 3306))

# ── Face Recognition ────────────────────────────────────
MODEL_PATH = os.environ.get("MODEL_PATH", "yolov8s-face-lindevs.pt")
