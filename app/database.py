"""
Database connection helper and table initialisation.
"""

import os
from dotenv import load_dotenv
import mysql.connector

load_dotenv()


def get_connection():
    """Return a new MySQL connection using environment variables."""
    return mysql.connector.connect(
        host=os.environ.get("MYSQLHOST", "localhost"),
        user=os.environ.get("MYSQLUSER", "root"),
        password=os.environ.get("MYSQLPASSWORD", ""),
        database=os.environ.get("MYSQLDATABASE", "attendance"),
        port=int(os.environ.get("MYSQLPORT", 3306)),
    )


def init_db():
    """Create all required tables if they don't already exist."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            name         VARCHAR(100),
            date         VARCHAR(20),
            time         VARCHAR(20),
            status       VARCHAR(20),
            late_minutes INT DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS faculty (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            name          VARCHAR(255) NOT NULL,
            email         VARCHAR(255) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_verified   INT DEFAULT 0,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            name          VARCHAR(255) NOT NULL,
            reg_number    VARCHAR(255) UNIQUE NOT NULL,
            college_email VARCHAR(255) UNIQUE NOT NULL,
            phone         VARCHAR(20) NOT NULL,
            password_hash TEXT NOT NULL,
            folder_name   VARCHAR(255) NOT NULL,
            registered_by VARCHAR(255),
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance_sessions (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            faculty_email   VARCHAR(255) NOT NULL,
            session_date    VARCHAR(20) NOT NULL,
            start_time      VARCHAR(20) NOT NULL,
            end_time        VARCHAR(20) NOT NULL,
            attendance_type VARCHAR(20) DEFAULT 'normal',
            is_active       INT DEFAULT 1,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS otp_store (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            target     VARCHAR(255) NOT NULL,
            otp_code   VARCHAR(10) NOT NULL,
            purpose    VARCHAR(50) NOT NULL,
            expires_at DATETIME NOT NULL,
            used       INT DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()
