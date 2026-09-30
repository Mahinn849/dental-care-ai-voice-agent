"""
CareVoice AI - CRM REST API Routes
Provides authenticated API endpoints for the Dental Clinic CRM Dashboard.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from pydantic import BaseModel
from backend.crm.auth import authenticate_clinic_staff, create_token, get_current_admin
from backend.crm.crm_service import (
    get_overview_metrics,
    check_pipeline_health,
    get_appointments,
    get_calendar_practice_grid,
    get_calls_history,
    get_patients_directory,
    get_analytics_metrics,
    create_appointment_manual,
    delete_appointment_record,
    purge_all_test_appointments,
    sync_google_calendar_event,
)

router = APIRouter(prefix="/api/crm", tags=["clinic-crm"])


# ==============================================================================
# Authentication Schemas & Routes
# ==============================================================================

class LoginRequest(BaseModel):
    username: str
    password: Optional[str] = None


@router.post("/auth/login")
async def crm_login(payload: LoginRequest, response: Response):
    """Authenticates clinic staff via username/password or quick PIN."""
    user = authenticate_clinic_staff(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid clinic credentials or PIN.")
        
    token = create_token(user)
    # Set secure session cookie
    response.set_cookie(
        key="crm_session",
        value=token,
        httponly=True,
        max_age=60 * 60 * 24,
        samesite="lax",
    )
    return {
        "status": "success",
        "token": token,
        "user": user,
        "data": {
            "token": token,
            "user": user,
        },
    }


@router.post("/auth/logout")
async def crm_logout(response: Response):
    """Logs out clinic staff by clearing the session cookie."""
    response.delete_cookie(key="crm_session")
    return {"status": "success", "message": "Logged out successfully."}


@router.get("/auth/me")
async def crm_me(current_user: dict = Depends(get_current_admin)):
    """Returns profile information for the authenticated clinic user."""
    return {"status": "success", "user": current_user, "data": current_user}


# ==============================================================================
# Overview & Pipeline Health
# ==============================================================================

@router.get("/overview")
async def crm_overview(current_user: dict = Depends(get_current_admin)):
    """Returns overview statistics, conversion funnel, and automation health."""
    metrics = get_overview_metrics()
    health = await check_pipeline_health()
    return {
        "status": "success",
        "data": {
            **metrics,
            "pipeline_health": health,
        }
    }


# ==============================================================================
# Appointments & Operational Practice Grid (Calendar)
# ==============================================================================

class AppointmentCreateRequest(BaseModel):
    patient_name: str
    phone_number: str
    appointment_date: str
    appointment_time: str
    service: Optional[str] = "General Dentistry"
    patient_type: Optional[str] = "Existing Patient"
    insurance: Optional[str] = "Self Pay"
    notes: Optional[str] = None


@router.get("/appointments")
async def crm_appointments(
    search: Optional[str] = None,
    status: Optional[str] = "all",
    date: Optional[str] = None,
    patient_type: Optional[str] = "all",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_admin),
):
    """Returns paginated, searchable clinic appointments."""
    res = get_appointments(
        search=search,
        status=status,
        date_filter=date,
        patient_type=patient_type,
        limit=limit,
        offset=offset,
    )
    return {
        "status": "success",
        "data": {
            **res,
            "appointments": res.get("items", []),
        }
    }


@router.post("/appointments")
async def crm_create_appointment(
    payload: AppointmentCreateRequest,
    current_user: dict = Depends(get_current_admin),
):
    """Allows clinic staff to manually create an appointment from the dashboard."""
    try:
        res = create_appointment_manual(payload.model_dump())
        return {"status": "success", "data": res}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.delete("/appointments/{appointment_id}")
async def crm_delete_appointment(
    appointment_id: int,
    current_user: dict = Depends(get_current_admin),
):
    """Deletes an appointment by ID."""
    try:
        res = delete_appointment_record(appointment_id)
        return {"status": "success", "data": res}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))


@router.post("/appointments/purge-test-data")
async def crm_purge_test_data(current_user: dict = Depends(get_current_admin)):
    """Purges all test appointments, calls, and patients so CRM starts 100% clean."""
    res = purge_all_test_appointments()
    return {"status": "success", "data": res}


@router.get("/calendar")
async def crm_calendar(
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    current_user: dict = Depends(get_current_admin),
):
    """Returns events formatted for the Operational Practice Grid (Month/Week/Day)."""
    import calendar as py_calendar
    from datetime import datetime
    
    if not start_date or not end_date:
        if month and len(month.split("-")) == 2:
            try:
                y, m = map(int, month.split("-"))
                _, last_day = py_calendar.monthrange(y, m)
                start_date = f"{y:04d}-{m:02d}-01"
                end_date = f"{y:04d}-{m:02d}-{last_day:02d}"
            except Exception:
                pass
        if not start_date or not end_date:
            now = datetime.now()
            _, last_day = py_calendar.monthrange(now.year, now.month)
            start_date = f"{now.year:04d}-{now.month:02d}-01"
            end_date = f"{now.year:04d}-{now.month:02d}-{last_day:02d}"

    events = get_calendar_practice_grid(start_date, end_date)
    return {"status": "success", "data": {"events": events, "start_date": start_date, "end_date": end_date}}


# ==============================================================================
# AI Calls & Transcripts
# ==============================================================================

@router.get("/calls")
async def crm_calls(
    search: Optional[str] = None,
    status: Optional[str] = "all",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_admin),
):
    """Returns voice call history with durations, transcripts, and outcomes."""
    res = get_calls_history(search=search, status=status, limit=limit, offset=offset)
    return {
        "status": "success",
        "data": {
            **res,
            "calls": res.get("items", []),
        }
    }


# ==============================================================================
# Patients Directory
# ==============================================================================

@router.get("/patients")
async def crm_patients(
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_admin),
):
    """Returns central clinic patient list."""
    res = get_patients_directory(search=search, limit=limit, offset=offset)
    return {
        "status": "success",
        "data": {
            **res,
            "patients": res.get("items", []),
        }
    }


# ==============================================================================
# Analytics
# ==============================================================================

@router.get("/analytics")
async def crm_analytics(current_user: dict = Depends(get_current_admin)):
    """Returns real operational analytics for the 4 dashboard cards."""
    res = get_analytics_metrics()
    return {"status": "success", "data": res}


# ==============================================================================
# Live Sync
# ==============================================================================

@router.post("/sync")
async def crm_sync_system(current_user: dict = Depends(get_current_admin)):
    """Checks synchronization status across n8n, Google Calendar, and Google Sheets."""
    health = await check_pipeline_health()
    return {
        "status": "success",
        "synced_at": "Just now",
        "pipeline": health,
    }


# ==============================================================================
# Inbound Webhook for Real-Time Google Calendar & Google Sheets Sync
# ==============================================================================

@router.post("/webhooks/google-calendar-sync")
async def crm_google_calendar_webhook(request: Request):
    """
    Public webhook for n8n Google Calendar / Google Sheets trigger.
    Automatically upserts or deletes appointments in real time when modified or created in Google Calendar.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    print(f"[CRM Webhook] Received Google Calendar event: {payload}")
    result = sync_google_calendar_event(payload)
    return {
        "status": "success",
        "message": "Calendar event synced with CRM database",
        "data": result,
    }
