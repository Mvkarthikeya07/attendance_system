"""Gunicorn configuration for Render deployment."""

import os

# Bind to PORT env var (Render sets this)
bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"

# Single worker to stay within 512 MB RAM
workers = 1

# Use gevent async worker so the MJPEG streaming endpoint
# (/video_feed) doesn't block/timeout the entire worker.
worker_class = "gevent"

# Disable worker timeout — the video feed is a long-lived stream
timeout = 120

# Preload the app so the YOLO model is loaded once in the master
# process and shared via copy-on-write with workers.
preload_app = True

# Limit request line & header sizes (sane defaults)
limit_request_line = 8190
limit_request_field_size = 8190

# Access log to stdout
accesslog = "-"
