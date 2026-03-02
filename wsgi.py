"""WSGI entrypoint for Render, Vercel, and other platforms.

Gunicorn uses:  gunicorn wsgi:app -c gunicorn.conf.py
"""

from app import app

# Only runs when executed directly (not via gunicorn)
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
