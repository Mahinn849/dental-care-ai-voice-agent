import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.crm.db import init_db, get_db
from backend.crm.crm_service import (
    sync_google_calendar_event,
    delete_appointment_record,
    purge_all_test_appointments,
    get_appointments,
    get_calendar_practice_grid
)


def run_crm_sync_integration_tests():
    init_db()
    # Clean purge
    purge_all_test_appointments()
    assert get_appointments()["total"] == 0

    # 1. Event Created
    gcal_event_create = {
        "id": "gcal_evt_integ_01",
        "status": "confirmed",
        "summary": "ASAD ULLAH - Teeth Whitening",
        "description": "Phone: 0312-3456789\nPatient Type: New Patient\nInsurance: MetLife",
        "start": {"dateTime": "2026-10-15T11:00:00+05:00"},
        "end": {"dateTime": "2026-10-15T11:45:00+05:00"}
    }
    sync_res = sync_google_calendar_event(gcal_event_create)
    assert sync_res["status"] == "success"
    assert sync_res["action"] == "upsert"

    apts = get_appointments()["items"]
    assert len(apts) == 1
    assert apts[0]["patient_name"] == "ASAD ULLAH"
    assert apts[0]["appointment_date"] == "2026-10-15"
    print("PASS: Event Created sync verified.")

    # 2. Event Updated / Rescheduled
    gcal_event_update = {
        "id": "gcal_evt_integ_01",
        "status": "confirmed",
        "summary": "ASAD ULLAH - Teeth Whitening & Cleaning",
        "description": "Phone: 0312-3456789\nPatient Type: Existing Patient\nInsurance: MetLife",
        "start": {"dateTime": "2026-10-16T14:30:00+05:00"},
        "end": {"dateTime": "2026-10-16T15:15:00+05:00"}
    }
    sync_update_res = sync_google_calendar_event(gcal_event_update)
    apts_after_update = get_appointments()["items"]
    assert len(apts_after_update) == 1
    assert apts_after_update[0]["appointment_date"] == "2026-10-16"
    assert apts_after_update[0]["appointment_time"] == "14:30"
    print("PASS: Event Rescheduled sync verified.")

    # 3. Event Deleted / Cancelled
    gcal_event_delete = {
        "id": "gcal_evt_integ_01",
        "status": "cancelled",
        "action": "delete"
    }
    sync_del_res = sync_google_calendar_event(gcal_event_delete)
    apts_after_del = get_appointments()["items"]
    assert len(apts_after_del) == 0
    print("PASS: Event Deleted sync verified.")

    # Cleanup
    purge_all_test_appointments()
    print("\nALL CRM GOOGLE CALENDAR SYNC INTEGRATION TESTS PASSED!")


if __name__ == "__main__":
    run_crm_sync_integration_tests()
