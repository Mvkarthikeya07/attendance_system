"""Gunicorn configuration for Render deployment."""

import os

# Bind to PORT env var (Render sets this)
bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"

# Single worker to stay within 512 MB RAM
workers = 1

# No MJPEG streaming anymore, so default sync worker is fine.
# Increase timeout so the YOLO model has time to load at startup.
timeout = 120

# Preload the app so the YOLO model is loaded once in the master
# process and shared via copy-on-write with workers.
preload_app = True

# Limit request line & header sizes (sane defaults)
limit_request_line = 8190
limit_request_field_size = 8190

# Access log to stdout
accesslog = "-"
errorlog = "-"
loglevel = "info"
