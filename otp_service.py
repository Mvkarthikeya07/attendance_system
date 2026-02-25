"""
otp_service.py  –  Email OTP (SMTP) + SMS OTP (Twilio) + Attendance Notification
==================================================================================
Configure credentials in config_new.py (see that file for instructions).
This file is purely additive and does NOT touch any existing code.

SMS provider: Twilio (free tier works for small colleges)
Email provider: SMTP (Gmail / college SMTP)

If credentials are not configured, OTP is printed to the console (development mode).
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
#  CONFIGURE HERE  (or fill in config_new.py)
# ─────────────────────────────────────────────────────────────────────
try:
    from config_new import (
        SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM,
        TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM
    )
except ImportError:
    SMTP_HOST     = ""
    SMTP_PORT     = 587
    SMTP_USER     = ""
    SMTP_PASSWORD = ""
    SMTP_FROM     = ""
    TWILIO_SID    = ""
    TWILIO_TOKEN  = ""
    TWILIO_FROM   = ""

DEV_MODE = not (SMTP_USER and SMTP_PASSWORD)


# ─────────────────────────────────────────────────────────────────────
#  EMAIL OTP
# ─────────────────────────────────────────────────────────────────────
def send_email_otp(to_email: str, otp_code: str, purpose: str = "verification") -> dict:
    """
    Send OTP via email.
    purpose: 'signup' | 'reset' | 'login'
    Returns {'ok': bool, 'msg': str}
    """
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
          This OTP is valid for <strong>10 minutes</strong>. Do not share it with anyone.
        </p>
      </div>
    </body></html>
    """

    if DEV_MODE:
        logger.warning(f"[DEV MODE] Email OTP for {to_email}: {otp_code}")
        print(f"\n{'='*55}")
        print(f"  [DEV] Email OTP")
        print(f"  To      : {to_email}")
        print(f"  OTP     : {otp_code}")
        print(f"  Purpose : {purpose}")
        print(f"{'='*55}\n")
        return {"ok": True, "msg": f"[DEV] OTP printed to console: {otp_code}"}

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = SMTP_FROM or SMTP_USER
        msg["To"]      = to_email
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, msg.as_string())

        return {"ok": True, "msg": f"OTP sent to {to_email}"}
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return {"ok": False, "msg": f"Could not send email: {str(e)}"}


# ─────────────────────────────────────────────────────────────────────
#  SMS OTP / NOTIFICATION  (Twilio)
# ─────────────────────────────────────────────────────────────────────
def send_sms(to_phone: str, message: str) -> dict:
    """
    Send SMS via Twilio.
    Returns {'ok': bool, 'msg': str}
    """
    twilio_ready = bool(TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM)

    if not twilio_ready:
        logger.warning(f"[DEV MODE] SMS to {to_phone}: {message}")
        print(f"\n{'='*55}")
        print(f"  [DEV] SMS Notification")
        print(f"  To  : {to_phone}")
        print(f"  Msg : {message}")
        print(f"{'='*55}\n")
        return {"ok": True, "msg": "[DEV] SMS printed to console"}

    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        msg = client.messages.create(body=message, from_=TWILIO_FROM, to=to_phone)
        return {"ok": True, "msg": f"SMS sent: {msg.sid}"}
    except Exception as e:
        logger.error(f"SMS send failed: {e}")
        return {"ok": False, "msg": str(e)}


def send_sms_otp(to_phone: str, otp_code: str, purpose: str = "verification") -> dict:
    message = f"[Attendance System] Your OTP is {otp_code}. Valid for 10 minutes. Do not share."
    return send_sms(to_phone, message)


def notify_students_attendance_started(student_list: list, start_time: str, end_time: str) -> dict:
    """
    Send SMS to all students that attendance has started.
    student_list: list of (phone, name) tuples from auth_db.get_student_phones()
    """
    message = (
        f"[Attendance System] Attendance is now OPEN.\n"
        f"Start: {start_time}  |  Deadline: {end_time}\n"
        f"Be present before {end_time} to avoid being marked LATE."
    )
    results = {"sent": 0, "failed": 0, "errors": []}
    for phone, name in student_list:
        res = send_sms(phone, message)
        if res["ok"]:
            results["sent"] += 1
        else:
            results["failed"] += 1
            results["errors"].append(f"{name} ({phone}): {res['msg']}")
    return results


def notify_students_via_email(student_email_list: list, start_time: str, end_time: str) -> dict:
    """
    Send email notification to all students.
    student_email_list: list of (email, name) tuples.
    """
    results = {"sent": 0, "failed": 0}
    for email, name in student_email_list:
        body = f"""
        <html><body style="font-family:Arial,sans-serif;background:#f4f6f9;padding:30px">
          <div style="max-width:520px;margin:auto;background:#fff;border-radius:12px;
                      padding:32px;box-shadow:0 2px 12px rgba(0,0,0,.1)">
            <h2 style="color:#4f46e5;margin:0 0 6px">Attendance Started</h2>
            <p style="color:#555">Hello <strong>{name}</strong>,</p>
            <p style="color:#555">Attendance is now <strong>OPEN</strong>.</p>
            <table style="width:100%;border-collapse:collapse;margin:16px 0">
              <tr>
                <td style="padding:8px 12px;background:#f0f0ff;border-radius:6px 0 0 6px">
                  Start Time</td>
                <td style="padding:8px 12px;background:#e8eaff;font-weight:bold">{start_time}</td>
              </tr>
              <tr>
                <td style="padding:8px 12px;background:#fff3e0;border-radius:6px 0 0 6px">
                  Deadline</td>
                <td style="padding:8px 12px;background:#ffe8cc;font-weight:bold">{end_time}</td>
              </tr>
            </table>
            <p style="color:#888;font-size:13px">
              Students arriving after the deadline will be marked <strong>LATE</strong>.
            </p>
          </div>
        </body></html>
        """
        if DEV_MODE:
            print(f"  [DEV] Attendance email → {email} ({name})")
            results["sent"] += 1
            continue
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = "Attendance is Now Open – Please Be Present"
            msg["From"]    = SMTP_FROM or SMTP_USER
            msg["To"]      = email
            msg.attach(MIMEText(body, "html"))
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo()
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, email, msg.as_string())
            results["sent"] += 1
        except Exception as e:
            logger.error(f"Email to {email} failed: {e}")
            results["failed"] += 1
    return results
