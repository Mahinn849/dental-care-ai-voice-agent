import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import json
from backend.tools.appointment_tools import (
    dental_check_appointment_availability,
    dental_clinic_appointment,
    APPOINTMENT_TOOLS,
    N8N_DENTAL_CHECK_AVAILABILITY_WEBHOOK_URL,
    N8N_DENTAL_CLINIC_APPOINTMENT_WEBHOOK_URL,
)
from backend.services.browser_voice_service import build_system_prompt, GREETING_TEXT

def test_tools_schema():
    assert len(APPOINTMENT_TOOLS) == 2, f"Expected 2 tools, got {len(APPOINTMENT_TOOLS)}"
    tool_map = {t["function"]["name"]: t["function"] for t in APPOINTMENT_TOOLS}
    
    # 1. dental_check_appointment_availability
    assert "dental_check_appointment_availability" in tool_map, "Missing dental_check_appointment_availability"
    avail_fn = tool_map["dental_check_appointment_availability"]
    avail_props = avail_fn["parameters"]["properties"]
    assert len(avail_props) == 3, f"Expected 3 parameters for avail tool, got {len(avail_props)}: {list(avail_props.keys())}"
    assert set(avail_props.keys()) == {"appointmentDate", "type", "appointmentTime"}
    assert set(avail_fn["parameters"]["required"]) == {"appointmentDate", "type", "appointmentTime"}
    print("PASS: dental_check_appointment_availability schema matches exactly 3 required parameters.")

    # 2. dental-clinic-appointment
    assert "dental-clinic-appointment" in tool_map, "Missing dental-clinic-appointment"
    clinic_fn = tool_map["dental-clinic-appointment"]
    clinic_props = clinic_fn["parameters"]["properties"]
    expected_13 = {
        "dateOfBirth",
        "type",
        "patientType",
        "newAppointmentDate",
        "insurance",
        "reasonForVisit",
        "appointmentTime",
        "oldAppointmentTime",
        "phoneNumber",
        "newAppointmentTime",
        "callerName",
        "oldAppointmentDate",
        "appointmentDate",
    }
    assert len(clinic_props) == 13, f"Expected 13 parameters, got {len(clinic_props)}: {list(clinic_props.keys())}"
    assert set(clinic_props.keys()) == expected_13, f"Properties mismatch: {set(clinic_props.keys()) ^ expected_13}"
    assert set(clinic_fn["parameters"]["required"]) == {"type", "callerName", "phoneNumber"}
    print("PASS: dental-clinic-appointment schema matches exactly 13 parameters with 3 required.")

def test_webhooks():
    assert "dental_check_appointment_availability" in N8N_DENTAL_CHECK_AVAILABILITY_WEBHOOK_URL
    assert "dental-clinic-appointment" in N8N_DENTAL_CLINIC_APPOINTMENT_WEBHOOK_URL
    print(f"PASS: Webhook 1 URL = {N8N_DENTAL_CHECK_AVAILABILITY_WEBHOOK_URL}")
    print(f"PASS: Webhook 2 URL = {N8N_DENTAL_CLINIC_APPOINTMENT_WEBHOOK_URL}")

def test_prompt_and_greeting():
    prompt = build_system_prompt()
    assert "Absolute dental clinic in Las Vegas" in prompt
    assert "8380 W Cheyenne Ave Ste 102" in prompt
    assert "dental-clinic-appointment" in prompt
    assert "dental_check_appointment_availability" in prompt
    assert "FYZICAL" not in prompt
    assert "Absolute Dental" in GREETING_TEXT
    print("PASS: System prompt and greeting are for Absolute Dental Clinic in Las Vegas.")

if __name__ == "__main__":
    test_tools_schema()
    test_webhooks()
    test_prompt_and_greeting()
    print("\nALL DENTAL CLINIC INTEGRATION TESTS PASSED SUCCESSFULLY!")
