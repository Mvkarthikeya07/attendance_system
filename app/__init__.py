"""
Attendance System — Flask Application Factory
"""

import os
from flask import Flask
from dotenv import load_dotenv

load_dotenv()


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev_fallback_key")

    # Initialise database tables
    from app.database import init_db
    init_db()

    # Register all blueprints
    from app.routes import register_blueprints
    register_blueprints(app)

    return app


# Expose at module level so `gunicorn app:app` can find it
app = create_app()
