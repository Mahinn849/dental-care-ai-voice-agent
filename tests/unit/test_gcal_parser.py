import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.crm.crm_service import parse_google_calendar_event


def test_gcal_event_creation_parsing():
    raw_event = {
        "id": "evt_sample_001",
        "summary": "HAMZA AHMED - Teeth Cleaning",
        "description": "Phone: +1 702 555 9999\nType: New Patient\nInsurance: Delta Dental",
        "start": {"dateTime": "2026-10-12T16:00:00+05:00"},
        "status": "confirmed"
    }
    parsed = parse_google_calendar_event(raw_event)
    assert parsed["action"] == "upsert"
    assert parsed["patient_name"] == "HAMZA AHMED"
    assert parsed["phone_number"] == "+1 702 555 9999"
    assert parsed["appointment_date"] == "2026-10-12"
    assert parsed["appointment_time"] == "16:00"
    assert parsed["service"] == "Teeth Cleaning"
    assert parsed["patient_type"] == "New Patient"
    print("PASS: test_gcal_event_creation_parsing passed.")


def test_gcal_event_cancellation_parsing():
    raw_event = {
        "id": "evt_sample_001",
        "status": "cancelled"
    }
    parsed = parse_google_calendar_event(raw_event)
    assert parsed["action"] == "delete"
    assert parsed["event_id"] == "evt_sample_001"
    print("PASS: test_gcal_event_cancellation_parsing passed.")


if __name__ == "__main__":
    test_gcal_event_creation_parsing()
    test_gcal_event_cancellation_parsing()
    print("\nALL GOOGLE CALENDAR PARSER TESTS PASSED!")
