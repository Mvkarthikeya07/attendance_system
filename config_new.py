# config_new.py  –  Credentials for Email OTP + SMS Notifications
# =================================================================
# Fill in your real credentials below.
# Without credentials the system runs in DEV MODE:
#   OTPs and SMS are printed to the terminal instead of being sent.
#
# ── GMAIL SETUP ──────────────────────────────────────────────────
# 1. Enable 2-Factor Authentication on your Gmail account
# 2. Go to https://myaccount.google.com/apppasswords
# 3. Create App Password → select "Mail"
# 4. Paste the 16-character password below (remove spaces)
#
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = "your_email@gmail.com"        # your Gmail address
SMTP_PASSWORD = "xxxxxxxxxxxxxxxxxxxx"         # 16-char App Password (no spaces)
SMTP_FROM     = "Attendance System <your_email@gmail.com>"

# ── TWILIO SMS SETUP ─────────────────────────────────────────────
# Free account: https://www.twilio.com/try-twilio
#
TWILIO_SID   = "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"   # Account SID
TWILIO_TOKEN = "your_auth_token_here"                 # Auth Token
TWILIO_FROM  = "+1415XXXXXXX"                         # Your Twilio number
