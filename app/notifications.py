"""
Email & SMS notification helpers.
Credentials are read from environment variables (see .env.example).
When credentials are missing the system runs in DEV MODE —
messages are printed to the terminal instead of being sent.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import *  # noqa: F403 — pulls whatever is available

# Safe defaults for optional notification services
import os
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "")
TWILIO_SID = os.environ.get("TWILIO_SID", "")
TWILIO_TOKEN = os.environ.get("TWILIO_TOKEN", "")
TWILIO_FROM = os.environ.get("TWILIO_FROM", "")

logger = logging.getLogger(__name__)

DEV_MODE = not (SMTP_USER and SMTP_PASSWORD)


# ── Email ───────────────────────────────────────────────────────────

def send_email_otp(to_email: str, otp_code: str, purpose: str = "verification") -> dict:
    subject_map = {
        "signup": "Verify your Attendance System account",
        "reset":  "Reset your Attendance System password",
        "login":  "Your login OTP – Attendance System",
    }
    subject = subject_map.get(purpose, "Your OTP – Attendance System")

    body = f"""
    <html><body style="font-family:Arial,sans-serif;background:#f4f6f9;padding:30px">
      <div style="max-width:480px;margin:auto;background:#fff;border-radius:12px;
                  padding:32px;box-shadow:0 2px 12px rgba(0,0,0,.1)">
        <h2 style="color:#4f46e5;margin:0 0 8px">Attendance System</h2>
        <p style="color:#555;margin:0 0 24px">Your One-Time Password (OTP):</p>
        <div style="background:#f0f0ff;border-radius:8px;padding:18px 24px;
                    text-align:center;letter-spacing:8px;font-size:32px;
                    font-weight:bold;color:#4f46e5">{otp_code}</div>
        <p style="color:#888;font-size:13px;margin:20px 0 0">
          Valid for <strong>10 minutes</strong>. Do not share.
        </p>
      </div>
    </body></html>
    """

    if DEV_MODE:
        print(f"\n[DEV] Email OTP → {to_email}: {otp_code} ({purpose})")
        return {"ok": True, "msg": f"[DEV] OTP: {otp_code}"}

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM or SMTP_USER
        msg["To"] = to_email
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, msg.as_string())

        return {"ok": True, "msg": f"OTP sent to {to_email}"}
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return {"ok": False, "msg": str(e)}


# ── SMS (Twilio) ────────────────────────────────────────────────────

def send_sms(to_phone: str, message: str) -> dict:
    twilio_ready = bool(TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM)

    if not twilio_ready:
        print(f"\n[DEV] SMS → {to_phone}: {message}")
        return {"ok": True, "msg": "[DEV] SMS printed to console"}

    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        msg = client.messages.create(body=message, from_=TWILIO_FROM, to=to_phone)
        return {"ok": True, "msg": f"SMS sent: {msg.sid}"}
    except Exception as e:
        logger.error(f"SMS failed: {e}")
        return {"ok": False, "msg": str(e)}


def send_sms_otp(to_phone: str, otp_code: str, purpose: str = "verification") -> dict:
    return send_sms(to_phone, f"[Attendance] OTP: {otp_code}. Valid 10 min.")


def notify_students_attendance(student_phones: list, start_time: str, end_time: str):
    """Notify all students via SMS that attendance has started."""
    message = (
        f"[Attendance] Session OPEN {start_time}–{end_time}. "
        f"Be present before {end_time} to avoid LATE."
    )
    sent, failed = 0, 0
    for phone, name in student_phones:
        res = send_sms(phone, message)
        sent += 1 if res["ok"] else 0
        failed += 0 if res["ok"] else 1
    return {"sent": sent, "failed": failed}


def notify_students_email(student_emails: list, start_time: str, end_time: str):
    """Notify all students via email that attendance has started."""
    sent, failed = 0, 0
    for email, name in student_emails:
        body = f"""
        <html><body style="font-family:Arial,sans-serif;padding:30px">
          <div style="max-width:520px;margin:auto;background:#fff;border-radius:12px;
                      padding:32px;box-shadow:0 2px 12px rgba(0,0,0,.1)">
            <h2 style="color:#4f46e5">Attendance Started</h2>
            <p>Hello <strong>{name}</strong>, attendance is <strong>OPEN</strong>.</p>
            <p>Start: <strong>{start_time}</strong> | Deadline: <strong>{end_time}</strong></p>
            <p style="color:#888;font-size:13px">
              Students arriving after the deadline will be marked <strong>LATE</strong>.
            </p>
          </div>
        </body></html>
        """
        if DEV_MODE:
            print(f"  [DEV] Attendance email → {email}")
            sent += 1
            continue
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = "Attendance is Now Open"
            msg["From"] = SMTP_FROM or SMTP_USER
            msg["To"] = email
            msg.attach(MIMEText(body, "html"))
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo()
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, email, msg.as_string())
            sent += 1
        except Exception as e:
            logger.error(f"Email to {email} failed: {e}")
            failed += 1
    return {"sent": sent, "failed": failed}
