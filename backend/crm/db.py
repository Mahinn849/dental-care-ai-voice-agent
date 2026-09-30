"""
CareVoice AI - CRM Database Manager
Lightweight, resilient SQLite database for Absolute Dental clinic operations.
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

CRM_DB_PATH = Path(os.getenv("CRM_DB_PATH", str(Path(__file__).resolve().parent / "clinic_crm.db")))


def get_db_connection() -> sqlite3.Connection:
    """Creates a connection with Row factory and WAL mode for high concurrency."""
    conn = sqlite3.connect(str(CRM_DB_PATH), timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_db():
    """Context manager for database operations with automatic commit and rollback."""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initializes the CRM database schema and indexes."""
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'admin',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            phone_number TEXT NOT NULL,
            appointment_date TEXT NOT NULL,
            appointment_time TEXT NOT NULL,
            service TEXT DEFAULT 'General Dentistry',
            patient_type TEXT DEFAULT 'Existing Patient',
            reason_for_visit TEXT,
            insurance TEXT,
            status TEXT DEFAULT 'confirmed',
            google_calendar_event_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            caller_name TEXT,
            phone_number TEXT,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP NOT NULL,
            duration_seconds INTEGER DEFAULT 0,
            status TEXT DEFAULT 'completed',
            intent TEXT,
            transcript_json TEXT,
            outcome TEXT,
            tool_calls_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            date_of_birth TEXT,
            patient_type TEXT DEFAULT 'Existing Patient',
            insurance TEXT,
            last_visit TEXT,
            total_visits INTEGER DEFAULT 1,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS appointment_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id INTEGER,
            action_type TEXT NOT NULL,
            action_result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(appointment_date);
        CREATE INDEX IF NOT EXISTS idx_appointments_phone ON appointments(phone_number);
        CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);
        CREATE INDEX IF NOT EXISTS idx_calls_session ON calls(session_id);
        CREATE INDEX IF NOT EXISTS idx_calls_created ON calls(created_at);
        CREATE INDEX IF NOT EXISTS idx_patients_phone ON patients(phone);
        """)
    print("[CRM DB] Schema initialized successfully at:", CRM_DB_PATH)


if __name__ == "__main__":
    init_db()
