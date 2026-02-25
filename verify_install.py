#!/usr/bin/env python3
"""
Installation Verification Script
Run this to check if everything is set up correctly
"""

import sys
import os

print("=" * 60)
print("🔍 ATTENDANCE SYSTEM - INSTALLATION VERIFICATION")
print("=" * 60)

# Check Python version
print("\n1️⃣ Checking Python version...")
if sys.version_info < (3, 7):
    print("   ❌ Python 3.7+ required. You have:", sys.version)
    sys.exit(1)
else:
    print(f"   ✅ Python {sys.version_info.major}.{sys.version_info.minor} OK")

# Check required modules
print("\n2️⃣ Checking required modules...")
required_modules = {
    'flask': 'Flask',
    'cv2': 'opencv-contrib-python',
    'numpy': 'numpy',
    'twilio': 'twilio (optional)',
    'ultralytics': 'ultralytics'
}

missing = []
for module, package in required_modules.items():
    try:
        __import__(module)
        print(f"   ✅ {package}")
    except ImportError:
        print(f"   ❌ {package} - MISSING")
        missing.append(package)

if missing:
    print(f"\n   To install missing packages:")
    print(f"   pip install {' '.join(missing)}")

# Check file structure
print("\n3️⃣ Checking file structure...")
required_files = [
    'app.py',
    'app_extension.py',
    'auth_db.py',
    'camera.py',
    'otp_service.py',
    'config_new.py',
    'train_model.py',
    'requirements.txt',
    'templates/student_login.html',
    'templates/student_register.html',
    'templates/student_dashboard.html',
    'templates/faculty_login.html',
    'templates/faculty_schedule.html'
]

for file in required_files:
    if os.path.exists(file):
        print(f"   ✅ {file}")
    else:
        print(f"   ❌ {file} - MISSING")

# Check configuration
print("\n4️⃣ Checking configuration...")
try:
    from config_new import SMTP_USER, TWILIO_SID
    if SMTP_USER == "your_email@gmail.com":
        print("   ⚠️  Email not configured (will use DEV mode)")
    else:
        print(f"   ✅ Email configured: {SMTP_USER}")
    
    if TWILIO_SID.startswith("ACxxxx"):
        print("   ⚠️  SMS not configured (will use DEV mode)")
    else:
        print(f"   ✅ SMS configured")
except Exception as e:
    print(f"   ❌ Configuration error: {e}")

# Create necessary directories
print("\n5️⃣ Creating directories...")
for directory in ['database', 'dataset']:
    os.makedirs(directory, exist_ok=True)
    print(f"   ✅ {directory}/")

print("\n" + "=" * 60)
if missing:
    print("⚠️  SETUP INCOMPLETE - Install missing packages")
    print(f"   pip install {' '.join(missing)}")
else:
    print("✅ SETUP COMPLETE - Ready to run!")
    print("\n   Start the server:")
    print("   python app.py")
    print("\n   Access points:")
    print("   • Students: http://localhost:5000/student/login")
    print("   • Faculty:  http://localhost:5000/faculty/login")
    print("   • Admin:    http://localhost:5000/")
print("=" * 60)
