import asyncio
import os
import sys
import json
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from openai import AsyncOpenAI

from backend.tools.appointment_tools import (
    check_appointment_availability,
    clinicappointment,
    APPOINTMENT_TOOLS,
)
from backend.services.browser_voice_service import build_system_prompt

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

async def test_direct_tools():
    print("=" * 60)
    print("1. DIRECT TOOL INVOCATION TESTS")
    print("=" * 60)

    # Test 1a: check_appointment_availability
    print("\n--- Test 1a: check_appointment_availability ---")
    res_avail = await check_appointment_availability("2026-09-25", "14:00")
    print("Result:", res_avail)

    # Test 1b: clinicappointment booking
    print("\n--- Test 1b: clinicappointment (appointment) ---")
    res_book = await clinicappointment(
        type="appointment",
        callerName="ALI MUNEER",
        phoneNumber="1234567890",
        appointmentDate="2026-09-25",
        appointmentTime="14:00",
        serviceInterest="Physical Therapy",
        patientType="New Patient",
        reasonForVisit="Knee pain",
        preferredLanguage="English",
    )
    print("Result:", res_book)

    # Test 1c: clinicappointment reschedule
    print("\n--- Test 1c: clinicappointment (reschedule) ---")
    res_resched = await clinicappointment(
        type="reschedule",
        callerName="ALI MUNEER",
        phoneNumber="1234567890",
        oldAppointmentDate="2026-09-25",
        oldAppointmentTime="14:00",
        newAppointmentDate="2026-09-28",
        newAppointmentTime="10:00",
    )
    print("Result:", res_resched)

    # Test 1d: clinicappointment cancel
    print("\n--- Test 1d: clinicappointment (cancel) ---")
    res_cancel = await clinicappointment(
        type="cancel",
        callerName="ALI MUNEER",
        phoneNumber="1234567890",
    )
    print("Result:", res_cancel)


async def test_dialog_flows():
    print("\n" + "=" * 60)
    print("2. OPENAI GPT-4.1-MINI DIALOG FLOW TESTS")
    print("=" * 60)

    system_prompt = build_system_prompt()

    # Case 1: Normal booking request (No date/time in first request)
    print("\n--- Case 1: User says 'I want to book an appointment' ---")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "I want to book an appointment."},
    ]
    resp = await client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        tools=APPOINTMENT_TOOLS,
        temperature=0.2,
    )
    choice = resp.choices[0].message
    print("Tool calls:", choice.tool_calls)
    print("Sophia response:", choice.content)
    assert choice.tool_calls is None, "Expected NO tool calls for initial general booking request!"

    # Case 2: Initial request contains BOTH date and time
    print("\n--- Case 2: User says 'I want to book an appointment this Friday at 2 PM' ---")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "I want to book an appointment this Friday at 2 PM."},
    ]
    resp = await client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        tools=APPOINTMENT_TOOLS,
        temperature=0.2,
    )
    choice = resp.choices[0].message
    print("Tool calls:", choice.tool_calls)
    assert choice.tool_calls is not None, "Expected tool call for initial date+time request!"
    fn_name = choice.tool_calls[0].function.name
    fn_args = json.loads(choice.tool_calls[0].function.arguments)
    print(f"Tool called: {fn_name} with args: {fn_args}")
    assert fn_name == "check_appointment_availability", f"Expected check_appointment_availability, got {fn_name}"

    # Case 3: Final confirmation in normal booking flow
    print("\n--- Case 3: Final confirmation for booking ---")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "I want to book an appointment."},
        {"role": "assistant", "content": "I'd be happy to help you book an appointment. To get everything scheduled, I'll need to collect a few details from you, starting with your full name."},
        {"role": "user", "content": "Ali Muneer"},
        {"role": "assistant", "content": "Are you a new or existing patient?"},
        {"role": "user", "content": "New patient"},
        {"role": "assistant", "content": "What brings you in today? Please briefly describe your condition."},
        {"role": "user", "content": "Knee pain after running"},
        {"role": "assistant", "content": "Which service are you interested in? We offer Physical Therapy, Balance Program, Post-Surgery Rehab, or Sports Injury Recovery."},
        {"role": "user", "content": "Physical Therapy"},
        {"role": "assistant", "content": "What date would you prefer for your appointment?"},
        {"role": "user", "content": "2026-09-25"},
        {"role": "assistant", "content": "What time works best for you? Our hours are Monday through Friday, 8 AM to 6 PM."},
        {"role": "user", "content": "14:00"},
        {"role": "assistant", "content": "May I have your phone number, please?"},
        {"role": "user", "content": "1234567890"},
        {"role": "assistant", "content": "What language do you prefer? English or Spanish?"},
        {"role": "user", "content": "English"},
        {"role": "assistant", "content": "Before I book your appointment, let me confirm the details. Your name is ALI MUNEER, your phone number is 1234567890, you're visiting for Knee pain after running, you're interested in Physical Therapy, your preferred appointment is on 2026-09-25 at 14:00. Is everything correct?"},
        {"role": "user", "content": "Yes, everything is correct."},
    ]
    resp = await client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        tools=APPOINTMENT_TOOLS,
        temperature=0.2,
    )
    choice = resp.choices[0].message
    print("Tool calls:", choice.tool_calls)
    assert choice.tool_calls is not None, "Expected clinicappointment tool call after confirmation!"
    fn_name = choice.tool_calls[0].function.name
    fn_args = json.loads(choice.tool_calls[0].function.arguments)
    print(f"Tool called: {fn_name} with args: {fn_args}")
    assert fn_name == "clinicappointment", f"Expected clinicappointment, got {fn_name}"
    assert fn_args.get("type") == "appointment", f"Expected type 'appointment', got {fn_args.get('type')}"
    assert fn_args.get("callerName") == "ALI MUNEER"
    assert fn_args.get("phoneNumber") == "1234567890"

    # Case 4: Busy slot handling with suggestedSlots
    print("\n--- Case 4: Busy slot handling with suggestedSlots ---")
    tool_call_id = choice.tool_calls[0].id
    messages.append({
        "role": "assistant",
        "content": None,
        "tool_calls": [choice.tool_calls[0].model_dump()],
    })
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": "clinicappointment",
        "content": json.dumps({
            "status": "slot_busy",
            "suggestedSlots": ["14:30", "15:30", "16:30"],
        }),
    })
    resp = await client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0.2,
    )
    print("Sophia response to busy slot:", resp.choices[0].message.content)

    # Case 5: Reschedule confirmation
    print("\n--- Case 5: Reschedule confirmation ---")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "I need to reschedule my appointment."},
        {"role": "assistant", "content": "May I have your full name, please?"},
        {"role": "user", "content": "Ali Muneer"},
        {"role": "assistant", "content": "May I have your phone number, please?"},
        {"role": "user", "content": "1234567890"},
        {"role": "assistant", "content": "Please tell me your current appointment date and time."},
        {"role": "user", "content": "September 25 at 2 PM"},
        {"role": "assistant", "content": "Please tell me your preferred new appointment date and time."},
        {"role": "user", "content": "September 28 at 10 AM"},
        {"role": "assistant", "content": "Current Appointment: Date 2026-09-25, Time 14:00. Requested Appointment: Date 2026-09-28, Time 10:00. Is that correct?"},
        {"role": "user", "content": "Yes, that's correct."},
    ]
    resp = await client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        tools=APPOINTMENT_TOOLS,
        temperature=0.2,
    )
    choice = resp.choices[0].message
    print("Tool calls:", choice.tool_calls)
    assert choice.tool_calls is not None, "Expected clinicappointment tool call after reschedule confirmation!"
    fn_name = choice.tool_calls[0].function.name
    fn_args = json.loads(choice.tool_calls[0].function.arguments)
    print(f"Tool called: {fn_name} with args: {fn_args}")
    assert fn_name == "clinicappointment", f"Expected clinicappointment, got {fn_name}"
    assert fn_args.get("type") == "reschedule", f"Expected type 'reschedule', got {fn_args.get('type')}"

    # Case 6: Cancel confirmation
    print("\n--- Case 6: Cancel confirmation ---")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "I want to cancel my appointment."},
        {"role": "assistant", "content": "May I have your full name, please?"},
        {"role": "user", "content": "Ali Muneer"},
        {"role": "assistant", "content": "May I have your phone number, please?"},
        {"role": "user", "content": "1234567890"},
    ]
    resp = await client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        tools=APPOINTMENT_TOOLS,
        temperature=0.2,
    )
    choice = resp.choices[0].message
    print("Tool calls:", choice.tool_calls)
    assert choice.tool_calls is not None, "Expected clinicappointment tool call after cancel info collected!"
    fn_name = choice.tool_calls[0].function.name
    fn_args = json.loads(choice.tool_calls[0].function.arguments)
    print(f"Tool called: {fn_name} with args: {fn_args}")
    assert fn_name == "clinicappointment", f"Expected clinicappointment, got {fn_name}"
    assert fn_args.get("type") == "cancel", f"Expected type 'cancel', got {fn_args.get('type')}"

    # Case 7: Hold Handling
    print("\n--- Case 7: Hold handling ---")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Hold on, one moment please."},
    ]
    resp = await client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        tools=APPOINTMENT_TOOLS,
        temperature=0.0,
    )
    print("Sophia response to hold:", resp.choices[0].message.content)
    assert "NO_RESPONSE_NEEDED" in resp.choices[0].message.content, "Expected NO_RESPONSE_NEEDED for hold request!"

    print("\nALL DIALOG FLOW TESTS PASSED SUCCESSFULLY!")

async def main():
    await test_direct_tools()
    await test_dialog_flows()

if __name__ == "__main__":
    asyncio.run(main())
