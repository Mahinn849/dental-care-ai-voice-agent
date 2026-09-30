"""
CareVoice AI - Dental Clinic Appointment Tools
Handles calendar availability checks and appointment booking/rescheduling/cancellation
via published n8n dental clinic webhooks.
"""

import os
import re
import json
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DENTAL_AVAILABILITY_WEBHOOK = "https://primary-production-930a9.up.railway.app/webhook/dental_check_appointment_availability"
N8N_DENTAL_CHECK_AVAILABILITY_WEBHOOK_URL = os.getenv(
    "N8N_DENTAL_CHECK_AVAILABILITY_WEBHOOK_URL",
    os.getenv("N8N_CHECK_APPOINTMENT_AVAILABILITY_WEBHOOK_URL", DEFAULT_DENTAL_AVAILABILITY_WEBHOOK)
)

DEFAULT_DENTAL_APPOINTMENT_WEBHOOK = "https://primary-production-930a9.up.railway.app/webhook/dental-clinic-appointment"
N8N_DENTAL_CLINIC_APPOINTMENT_WEBHOOK_URL = os.getenv(
    "N8N_DENTAL_CLINIC_APPOINTMENT_WEBHOOK_URL",
    os.getenv("N8N_CLINIC_APPOINTMENT_WEBHOOK_URL", DEFAULT_DENTAL_APPOINTMENT_WEBHOOK)
)

# Backwards compatibility constants
N8N_WEBHOOK_URL = N8N_DENTAL_CHECK_AVAILABILITY_WEBHOOK_URL
N8N_CLINIC_APPOINTMENT_WEBHOOK_URL = N8N_DENTAL_CLINIC_APPOINTMENT_WEBHOOK_URL


def _format_time_12h(time_str: str) -> str:
    """
    Converts any time representation to natural spoken format:
    - '14:00' -> '2 PM'
    - '10:00' -> '10 AM'
    - '2:00 PM' / '2:00 Pm' / '2:00pm' -> '2 PM'
    - '02:00 PM' -> '2 PM'
    - '14:30' -> '2:30 PM'
    - '2:30 PM' -> '2:30 PM'
    - '6:56 PM' -> '6:56 PM'
    """
    if not time_str:
        return ""
    try:
        s = str(time_str).strip()
        # Check if AM or PM is explicitly present
        m_ampm = re.search(r'(?i)\b(am|pm)\b', s)
        explicit_ampm = m_ampm.group(1).upper() if m_ampm else None

        # Remove AM/PM to isolate digits
        clean = re.sub(r'(?i)\s*(am|pm)\b', '', s).strip()
        parts = clean.split(":")
        h = int(parts[0])
        m_raw = parts[1] if len(parts) > 1 else "00"
        m = m_raw[:2].zfill(2)

        if explicit_ampm:
            ampm = explicit_ampm
            disp_h = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
        else:
            if h == 0:
                disp_h = 12
                ampm = "AM"
            elif 1 <= h <= 6:
                # In dental clinic context, times 1 to 6 are PM
                disp_h = h
                ampm = "PM"
            elif 7 <= h <= 11:
                disp_h = h
                ampm = "AM"
            elif h == 12:
                disp_h = 12
                ampm = "PM"
            else:
                disp_h = h - 12
                ampm = "PM"

        if m == "00":
            return f"{disp_h} {ampm}"
        return f"{disp_h}:{m} {ampm}"
    except Exception:
        return str(time_str)


def _build_natural_slots_message(requested_date: str, requested_time: str, suggested_slots: list) -> str:
    """
    Builds a natural conversational receptionist message for alternative slots.
    Avoids robotic numbering (1., 2.) and groups times smoothly.
    """
    req_t = _format_time_12h(requested_time) if requested_time else "that time"
    req_d = f" on {requested_date}" if requested_date else ""

    if not suggested_slots:
        return f"The requested appointment slot at {req_t}{req_d} is currently not available. Please let me know another date or time that might work for you."

    date_groups = {}
    for slot in suggested_slots:
        if isinstance(slot, dict):
            s_date = slot.get("appointmentDate") or requested_date or ""
            s_time = slot.get("appointmentTime") or slot.get("time") or slot.get("slot") or ""
            t_str = _format_time_12h(str(s_time)) if s_time else (slot.get("display") or "")
        elif isinstance(slot, str):
            s_date = requested_date or ""
            t_str = _format_time_12h(slot)
        else:
            continue

        if not t_str:
            continue
        if s_date not in date_groups:
            date_groups[s_date] = []
        if t_str not in date_groups[s_date]:
            date_groups[s_date].append(t_str)

    if not date_groups:
        return f"The requested appointment slot at {req_t}{req_d} is currently not available."

    # If all slots are on the requested date (or only 1 date)
    if len(date_groups) == 1:
        d = list(date_groups.keys())[0]
        times = date_groups[d]
        if len(times) == 1:
            times_phrase = times[0]
        elif len(times) == 2:
            times_phrase = f"{times[0]} and {times[1]}"
        else:
            times_phrase = f"{', '.join(times[:-1])}, and {times[-1]}"

        date_phrase = f" on {d}" if (d and d != requested_date) else ""
        return f"The requested slot at {req_t}{req_d} is not available, but we have openings{date_phrase} at {times_phrase}. Would any of those times work for you?"

    # If slots span multiple dates
    parts = []
    for d, times in date_groups.items():
        if len(times) == 1:
            times_phrase = times[0]
        elif len(times) == 2:
            times_phrase = f"{times[0]} and {times[1]}"
        else:
            times_phrase = f"{', '.join(times[:-1])}, and {times[-1]}"
        d_label = f"on {d}" if d else ""
        parts.append(f"{d_label} at {times_phrase}".strip())

    slots_phrase = ", or ".join(parts)
    return f"The requested slot at {req_t}{req_d} is not available, but we have openings {slots_phrase}. Would any of those work for you?"


async def dental_check_appointment_availability(
    appointmentDate: str,
    appointmentTime: str,
    type: str = "availability"
) -> dict:
    """
    Checks whether a specific date and time are available for a new appointment.
    Use only when the patient's first booking request already contains both a specific date
    and a specific time, before collecting any other patient information.
    Returns available or suggested alternative slots.
    
    Request body contains exactly 3 fields: type, appointmentDate, appointmentTime.
    """
    payload = {
        "type": "availability",
        "appointmentDate": appointmentDate.strip() if appointmentDate else "",
        "appointmentTime": appointmentTime.strip() if appointmentTime else "",
    }

    print(f"[TOOL] dental_check_appointment_availability called")
    print(f"[TOOL] Payload: {json.dumps(payload, indent=2)}")
    print(f"[TOOL] Sending request to n8n ({N8N_DENTAL_CHECK_AVAILABILITY_WEBHOOK_URL})...")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(N8N_DENTAL_CHECK_AVAILABILITY_WEBHOOK_URL, json=payload)
            print(f"[TOOL] n8n HTTP status: {response.status_code}")

            if response.status_code == 200:
                text = response.text.strip()
                if text:
                    try:
                        raw_data = response.json()
                    except json.JSONDecodeError:
                        raw_data = {"available": False, "raw_response": text, "message": "Could not parse calendar response."}

                    if isinstance(raw_data, list):
                        # n8n returned a list of suggested slots
                        slots = []
                        for item in raw_data:
                            if isinstance(item, dict):
                                t = item.get("appointmentTime") or item.get("time") or item.get("slot")
                                if t:
                                    slots.append(_format_time_12h(str(t)))
                            elif isinstance(item, str):
                                slots.append(_format_time_12h(item))
                        result = {
                            "available": False,
                            "status": "slot_busy",
                            "appointmentDate": payload["appointmentDate"],
                            "appointmentTime": payload["appointmentTime"],
                            "message": _build_natural_slots_message(payload["appointmentDate"], payload["appointmentTime"], slots),
                            "suggestedSlots": slots,
                        }
                    elif isinstance(raw_data, dict):
                        result = raw_data
                        # If unavailable but slots not formatted or in another key
                        if not result.get("available", False):
                            result["status"] = result.get("status", "slot_busy")
                            if "suggestedSlots" not in result:
                                found = result.get("slots") or result.get("availableSlots") or []
                                result["suggestedSlots"] = [_format_time_12h(str(s)) for s in found]
                            result["message"] = _build_natural_slots_message(
                                payload["appointmentDate"],
                                payload["appointmentTime"],
                                result.get("suggestedSlots", [])
                            )
                    else:
                        result = {
                            "available": False,
                            "status": "slot_busy",
                            "message": f"The requested appointment slot at {_format_time_12h(payload['appointmentTime'])} is not available."
                        }
                else:
                    # n8n webhook responded 200 with empty body (busy branch finished without Respond to Webhook node)
                    print("[TOOL Warning] n8n check availability returned 200 with empty body. Treating as unavailable.")
                    result = {
                        "available": False,
                        "status": "slot_busy",
                        "appointmentDate": payload["appointmentDate"],
                        "appointmentTime": payload["appointmentTime"],
                        "message": _build_natural_slots_message(payload["appointmentDate"], payload["appointmentTime"], []),
                        "suggestedSlots": [],
                    }
            else:
                result = {
                    "available": False,
                    "error": f"Calendar service returned status code {response.status_code}",
                }

    except httpx.TimeoutException:
        print("[TOOL Error] n8n check availability webhook request timed out.")
        result = {
            "available": False,
            "error": "Calendar availability service timed out. Please try again.",
        }
    except Exception as e:
        print(f"[TOOL Error] Failed to connect to n8n: {e}")
        result = {
            "available": False,
            "error": f"Could not connect to calendar availability service: {str(e)}",
        }

    print(f"[TOOL] n8n response received: {result}")
    print(f"[TOOL] Returning availability result to OpenAI")
    return result


async def dental_clinic_appointment(
    type: str,
    callerName: str,
    phoneNumber: str,
    appointmentDate: str = None,
    appointmentTime: str = None,
    dateOfBirth: str = None,
    patientType: str = None,
    reasonForVisit: str = None,
    insurance: str = None,
    oldAppointmentDate: str = None,
    oldAppointmentTime: str = None,
    newAppointmentDate: str = None,
    newAppointmentTime: str = None,
    **kwargs,
) -> dict:
    """
    Books, reschedules, or cancels a dental appointment at Absolute Dental.
    Dispatches request to published n8n dental-clinic-appointment webhook.
    
    Request body parameters are drawn from the 13 defined schema parameters:
    dateOfBirth, type, patientType, newAppointmentDate, insurance, reasonForVisit,
    appointmentTime, oldAppointmentTime, phoneNumber, newAppointmentTime, callerName,
    oldAppointmentDate, appointmentDate.
    """
    name_upper = callerName.strip().upper() if callerName else ""
    phone = phoneNumber.strip() if phoneNumber else ""
    action_type = type.strip().lower() if type else "appointment"

    if action_type == "appointment":
        payload = {
            "type": "appointment",
            "callerName": name_upper,
            "phoneNumber": phone,
            "dateOfBirth": dateOfBirth.strip() if dateOfBirth else "",
            "patientType": patientType.strip() if patientType else "",
            "reasonForVisit": reasonForVisit.strip() if reasonForVisit else "",
            "insurance": insurance.strip() if insurance else "",
            "appointmentDate": appointmentDate.strip() if appointmentDate else "",
            "appointmentTime": appointmentTime.strip() if appointmentTime else "",
        }
    elif action_type == "reschedule":
        payload = {
            "type": "reschedule",
            "callerName": name_upper,
            "phoneNumber": phone,
            "oldAppointmentDate": oldAppointmentDate.strip() if oldAppointmentDate else "",
            "oldAppointmentTime": oldAppointmentTime.strip() if oldAppointmentTime else "",
            "newAppointmentDate": newAppointmentDate.strip() if newAppointmentDate else "",
            "newAppointmentTime": newAppointmentTime.strip() if newAppointmentTime else "",
        }
    elif action_type == "cancel":
        payload = {
            "type": "cancel",
            "callerName": name_upper,
            "phoneNumber": phone,
        }
    else:
        payload = {
            "type": action_type,
            "callerName": name_upper,
            "phoneNumber": phone,
        }

    print(f"[TOOL] dental-clinic-appointment called with type: '{action_type}'")
    print(f"[TOOL] Payload: {json.dumps(payload, indent=2)}")
    print(f"[TOOL] Sending request to n8n ({N8N_DENTAL_CLINIC_APPOINTMENT_WEBHOOK_URL})...")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(N8N_DENTAL_CLINIC_APPOINTMENT_WEBHOOK_URL, json=payload)
            print(f"[TOOL] n8n HTTP status: {response.status_code}")

            if response.status_code == 200:
                text = response.text.strip()
                if text:
                    try:
                        result = response.json()
                        if isinstance(result, dict) and (result.get("status") == "slot_busy" or "suggestedSlots" in result):
                            req_d = payload.get("newAppointmentDate") or payload.get("appointmentDate") or ""
                            req_t = payload.get("newAppointmentTime") or payload.get("appointmentTime") or ""
                            result["message"] = _build_natural_slots_message(req_d, req_t, result.get("suggestedSlots", []))
                    except json.JSONDecodeError:
                        result = {"status": "success", "raw_response": text}
                else:
                    # n8n webhook responded 200 with empty body (workflow stopped before reaching a Respond to Webhook node)
                    print(f"[TOOL Warning] n8n returned 200 with empty body for action '{action_type}'. Workflow halted early.")
                    if action_type in ("reschedule", "cancel"):
                        result = {
                            "status": "error",
                            "error": f"Could not find an active appointment matching '{name_upper}' and phone '{phone}' in clinic records. Please verify the exact name and phone number used during booking.",
                        }
                    else:
                        result = {
                            "status": "error",
                            "error": f"The dental clinic service could not complete the appointment action '{action_type}'. Please check the details and try again.",
                        }
            else:
                result = {
                    "status": "error",
                    "error": f"Dental clinic service returned status code {response.status_code}",
                }

    except httpx.TimeoutException:
        print("[TOOL Error] n8n dental-clinic-appointment webhook request timed out.")
        result = {
            "status": "error",
            "error": "Dental appointment service timed out. Please try again.",
        }
    except Exception as e:
        print(f"[TOOL Error] Failed to connect to n8n dental-clinic-appointment: {e}")
        result = {
            "status": "error",
            "error": f"Could not connect to dental appointment service: {str(e)}",
        }

    print(f"[TOOL] n8n response received: {result}")
    print(f"[TOOL] Returning result to OpenAI")
    return result


# Backwards compatibility aliases
check_appointment_availability = dental_check_appointment_availability
clinicappointment = dental_clinic_appointment


# OpenAI Function Calling Tool Schemas
APPOINTMENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "dental_check_appointment_availability",
            "description": (
                "Checks whether a specific appointment date and time are available on the Absolute Dental clinic calendar. "
                "You MUST call this tool anytime the caller asks if a date or time is available, or provides a preferred appointment date and time. "
                "Returns availability status and suggested available alternative slots."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "appointmentDate": {
                        "type": "string",
                        "description": "Appointment date in YYYY-MM-DD format (e.g. '2026-09-29')",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["availability"],
                        "description": "Must be 'availability'",
                    },
                    "appointmentTime": {
                        "type": "string",
                        "description": "Appointment time in HH:MM 24-hour format (e.g. '14:00' for 2 PM)",
                    },
                },
                "required": ["appointmentDate", "type", "appointmentTime"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dental-clinic-appointment",
            "description": (
                "Books, reschedules, or cancels an appointment in the clinic appointment database and calendar via n8n. "
                "Use type 'appointment' after confirming all patient details to complete booking. "
                "Use type 'reschedule' to change an existing appointment date/time. "
                "Use type 'cancel' to cancel an existing appointment."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dateOfBirth": {
                        "type": "string",
                        "description": "Patient date of birth, YYYY-MM-DD",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["appointment", "reschedule", "cancel"],
                        "description": "The operation to perform: appointment, reschedule, or cancel",
                    },
                    "patientType": {
                        "type": "string",
                        "enum": ["New Patient", "Existing Patient"],
                        "description": "Required when type is appointment: 'New Patient' or 'Existing Patient'",
                    },
                    "newAppointmentDate": {
                        "type": "string",
                        "description": "New appointment date in YYYY-MM-DD format for reschedule",
                    },
                    "insurance": {
                        "type": "string",
                        "description": "Insurance company name, 'Self Pay', or 'Not Sure'",
                    },
                    "reasonForVisit": {
                        "type": "string",
                        "description": "Reason for the visit. Required when type is appointment",
                    },
                    "appointmentTime": {
                        "type": "string",
                        "description": "Appointment time, HH:MM in 24-hour format for booking",
                    },
                    "oldAppointmentTime": {
                        "type": "string",
                        "description": "Existing appointment time in HH:MM 24-hour format for reschedule",
                    },
                    "phoneNumber": {
                        "type": "string",
                        "description": "Patient phone number",
                    },
                    "newAppointmentTime": {
                        "type": "string",
                        "description": "New appointment time in HH:MM 24-hour format for reschedule",
                    },
                    "callerName": {
                        "type": "string",
                        "description": "Patient full name in UPPERCASE (e.g., 'ALI MUNEER')",
                    },
                    "oldAppointmentDate": {
                        "type": "string",
                        "description": "Existing appointment date in YYYY-MM-DD format for reschedule",
                    },
                    "appointmentDate": {
                        "type": "string",
                        "description": "Appointment date, YYYY-MM-DD format for booking",
                    },
                },
                "required": ["type", "callerName", "phoneNumber"],
                "additionalProperties": False,
            },
        },
    },
]
