"""Register all route blueprints with the Flask app."""

from app.routes.admin import admin_bp
from app.routes.faculty import faculty_bp
from app.routes.student import student_bp
from app.routes.attendance import attendance_bp


def register_blueprints(app):
    app.register_blueprint(admin_bp)
    app.register_blueprint(faculty_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(attendance_bp)
