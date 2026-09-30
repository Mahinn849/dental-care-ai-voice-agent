"""
CareVoice AI - Main FastAPI Application & Entrypoint
Serves browser voice interface and mounts WebSocket streaming endpoints.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Windows console encoding safeguard to prevent charmap UnicodeEncodeErrors
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.api.voice_routes import router as voice_router
from backend.api.crm_routes import router as crm_router
from backend.crm.db import init_db
from backend.crm.auth import ensure_admin_user

# Initialize CRM DB and default admin
try:
    init_db()
    ensure_admin_user()
except Exception as e:
    print(f"[Main Init Warning] {e}")

app = FastAPI(title="CareVoice AI - Healthcare Voice Receptionist & Clinic CRM")

# Enable CORS for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Voice WebSocket API & CRM REST API
app.include_router(voice_router)
app.include_router(crm_router)

# Mount Dashboard and Frontend static files
frontend_dir = root_dir / "frontend"
dashboard_dir = frontend_dir / "dashboard"

if dashboard_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=str(dashboard_dir), html=True), name="dashboard")

if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)
