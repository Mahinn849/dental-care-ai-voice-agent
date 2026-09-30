"""
CareVoice AI - CRM Authentication
Lightweight, secure session/token management for Absolute Dental clinic staff.
"""

import os
import hmac
import hashlib
import json
import base64
import time
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, Depends
from dotenv import load_dotenv
from backend.crm.db import get_db

load_dotenv()

CRM_ADMIN_USER = os.getenv("CRM_ADMIN_USER", "admin@absolutedental.com")
CRM_ADMIN_PASS = os.getenv("CRM_ADMIN_PASS", "AbsoluteDental2026!")
CRM_ADMIN_PIN = os.getenv("CRM_ADMIN_PIN", "2026")
CRM_SECRET_KEY = os.getenv("CRM_SECRET_KEY", "carevoice_dental_crm_secret_token_2026")
SESSION_TTL_SECONDS = 60 * 60 * 24  # 24 hours


def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Hashes a password using PBKDF2-HMAC-SHA256 with a unique salt."""
    if not salt:
        salt = os.urandom(16).hex()
    pwd_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000
    ).hex()
    return f"{salt}${pwd_hash}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verifies a plaintext password against a stored PBKDF2 hash."""
    try:
        salt, expected_hash = stored_hash.split("$")
        actual_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100_000
        ).hex()
        return hmac.compare_digest(actual_hash, expected_hash)
    except Exception:
        return False


def ensure_admin_user():
    """Ensures at least one admin user exists based on environment configuration."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM admin_users WHERE username = ?", (CRM_ADMIN_USER,)).fetchone()
        if not row:
            hashed = hash_password(CRM_ADMIN_PASS)
            conn.execute(
                "INSERT INTO admin_users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                (CRM_ADMIN_USER, CRM_ADMIN_USER, hashed, "super_admin")
            )
            print(f"[CRM Auth] Initialized default admin user: {CRM_ADMIN_USER}")


def create_token(payload: Dict[str, Any]) -> str:
    """Creates a URL-safe signed session token."""
    payload["exp"] = int(time.time()) + SESSION_TTL_SECONDS
    raw_json = json.dumps(payload, separators=(',', ':')).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(raw_json).decode("utf-8").rstrip("=")
    signature = hmac.new(CRM_SECRET_KEY.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{b64_payload}.{signature}"


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verifies and decodes a session token."""
    if not token or "." not in token:
        return None
    try:
        b64_payload, signature = token.split(".", 1)
        expected_sig = hmac.new(CRM_SECRET_KEY.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        
        # Add padding back if necessary
        padding = 4 - (len(b64_payload) % 4)
        if padding and padding != 4:
            b64_payload += "=" * padding
            
        raw_json = base64.urlsafe_b64decode(b64_payload.encode("utf-8")).decode("utf-8")
        data = json.loads(raw_json)
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None


def authenticate_clinic_staff(username_or_pin: str, password: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Authenticates staff via username/password or quick clinic PIN."""
    username_or_pin = (username_or_pin or "").strip()
    
    # 1. Quick Clinic PIN check
    if CRM_ADMIN_PIN and username_or_pin == CRM_ADMIN_PIN:
        return {
            "username": "clinic_staff",
            "name": "Hamayoon",
            "role": "Dental Clinic Admin",
            "auth_type": "pin"
        }
        
    # 2. Username + Password check
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, email, password_hash, role FROM admin_users WHERE username = ? OR email = ?",
            (username_or_pin, username_or_pin)
        ).fetchone()
        
        if row and password and verify_password(password, row["password_hash"]):
            return {
                "id": row["id"],
                "username": row["username"],
                "email": row["email"],
                "name": "Hamayoon",
                "role": "Dental Clinic Admin",
                "auth_type": "password"
            }
            
    # 3. Direct match against environment admin fallback
    if username_or_pin == CRM_ADMIN_USER and password == CRM_ADMIN_PASS:
        return {
            "username": CRM_ADMIN_USER,
            "name": "Hamayoon",
            "role": "Dental Clinic Admin",
            "auth_type": "env_fallback"
        }
        
    return None


async def get_current_admin(request: Request) -> Dict[str, Any]:
    """FastAPI dependency to protect CRM endpoints."""
    token = None
    # 1. Check Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    # 2. Check Cookie
    if not token:
        token = request.cookies.get("crm_session")
        
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required for Clinic CRM.")
        
    user_data = verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please log in.")
        
    return user_data
