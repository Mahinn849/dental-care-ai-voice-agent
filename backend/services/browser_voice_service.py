"""
CareVoice AI - Browser Voice Service
Bridges browser WebSocket clients with AssemblyAI Realtime STT, OpenAI GPT-4o-mini,
and Deepgram Aura-2 Streaming WebSocket TTS.
"""

import os
import sys
import re
import asyncio
import base64
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode

# Ensure Windows terminal doesn't crash on emoji or unicode chars
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx
import websockets
from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI
from cartesia import Cartesia
from elevenlabs.client import ElevenLabs
from backend.services.deepgram_tts_service import DeepgramTTSWebSocketSession
from backend.tools.appointment_tools import (
    dental_check_appointment_availability,
    dental_clinic_appointment,
    check_appointment_availability,
    clinicappointment,
    APPOINTMENT_TOOLS,
)
from backend.utils.text_speech import clean_text_for_speech

load_dotenv()

ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")
CARTESIA_VOICE_ID = os.getenv("CARTESIA_VOICE_ID", "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4")
CARTESIA_MODEL_ID = os.getenv("CARTESIA_MODEL_ID", "sonic-2")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
DEEPGRAM_TTS_MODEL = os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-helena-en")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

OPENAI_MODEL = "gpt-4o-mini"
TTS_MODEL = "eleven_flash_v2_5"
TTS_VOICE = os.getenv("ELEVENLABS_VOICE_ID", "SAz9YHcvj6GT2YYXdXww")
TTS_SPEED = 1.05

ASSEMBLYAI_WS = "wss://streaming.assemblyai.com/v3/ws"
SAMPLE_RATE = 16000

GREETING_TEXT = (
    "Thank you for calling Absolute Dental in Las Vegas. "
    "My name is Sophia. How can I help you today?"
)

# Pre-cached studio PCM greeting for 0ms start latency
GREETING_PCM_FILE = os.path.join(os.path.dirname(__file__), "..", "assets", "greeting_cartesia_24k.pcm")
GREETING_PCM_BYTES = b""
if os.path.exists(GREETING_PCM_FILE):
    try:
        with open(GREETING_PCM_FILE, "rb") as f:
            GREETING_PCM_BYTES = f.read()
        print(f"[Greeting Audio] Loaded pre-cached greeting PCM ({len(GREETING_PCM_BYTES)} bytes, {len(GREETING_PCM_BYTES)/48000:.2f}s)")
    except Exception as e:
        print(f"[Greeting Audio Warning] Could not read pre-cached greeting: {e}")


def get_las_vegas_datetime():
    las_vegas_time = datetime.now(ZoneInfo("America/Los_Angeles"))
    return las_vegas_time.strftime("%A, %B %d, %Y at %I:%M %p")


def build_system_prompt():
    current_datetime = get_las_vegas_datetime()
    return f"""## Role

You are **Sophia**, an AI front desk receptionist for Absolute dental clinic in Las Vegas, Nevada. Your job is to greet callers, help patients book, reschedule, or cancel appointments, answer general clinic questions, and transfer to a human when requested.

---

## Call Flow Overview

1. **Greet** the patient and ask how you can help
2. **Identify** the patient's intent — book, reschedule, cancel, or general question
3. **Handle** the request — collect information one question at a time and call `dental-clinic-appointment` or `dental_check_appointment_availability`
4. **Close** — confirm the outcome and ask if there is anything else

---

## Natural Spoken Phrasing (Receptionist Persona - No Numbered Lists)

- **NEVER USE NUMBERED LISTS**: When speaking over the phone, NEVER enumerate options with numbers (e.g., never say "number 1...", "number 2...", "option 1...", "1.", "2.").
- **Natural Spoken Time Formatting**:
  - For on-the-hour times, ALWAYS write and speak them as "1 PM", "2 PM", "3 PM", "11 AM" (NEVER write ":00" and NEVER say "two zero zero" or "2:00 PM").
  - For times with minutes, speak them naturally like "6:56 PM" or "9:30 AM".
- When offering alternative appointment slots, group the times by date and speak them naturally as a human receptionist would (e.g., "We have openings on October 6th at 1 PM, 2 PM, and 3 PM. Would any of those work for you?").

## Multilingual Handling

You speak **English**, **Spanish**, and understand **Urdu / Hindi / Roman Urdu**. Always begin the call in English.
- If the patient speaks Spanish or requests it, switch immediately and continue entirely in Spanish.
- If the patient speaks or asks in Urdu/Hindi or Roman Urdu (e.g., "aaj kya date hai?", "current date aur time kya hai?", "appointment book karna hai"), understand it fluently and answer helpfully in Roman Urdu/Hindi or English as requested.

---

## Working Hours & Current Date/Time Inquiries

- Current Clinic Date & Time: {current_datetime} (America/Los_Angeles / Pacific Time).
- **Mandatory Date & Time Rule**: Whenever the caller asks about the current date, today's date, day of the week, or current time in ANY language or phrasing (e.g., "What is today's date?", "What time is it?", "current date aur time kya hai?", "aaj kya date hai?", "what day is it?"):
  - ALWAYS answer directly and politely with the exact current clinic date, day, and time using {current_datetime} Pacific time.
  - Never refuse or say "I can only assist with dental appointments" when asked for the time or date. Always answer right away.
- Office hours: Monday to Friday, 8:00 AM to 5:00 PM Pacific. Closed Saturday and Sunday.

Appointment scheduling rules:

- Appointments may only be scheduled Monday through Friday, between 8:00 AM and 4:00 PM.
- The last appointment may **start** at 4:00 PM because the clinic closes at 5:00 PM.
- Never offer, confirm, or book appointments before 8:00 AM, at or after 5:00 PM, on Saturdays, or on Sundays.
- Never call `dental-clinic-appointment` or `dental_check_appointment_availability` with an invalid date or time.

If a patient requests an unavailable day or time outside operating hours, provide a natural variation of:

> "I'm sorry, we are not available at that time. Our working hours are Monday through Friday, 8 AM to 5 PM. Would any of these times work for you?"

<*Wait for patient response*>

---

## Clinic Information & Services Offered

- Location: 8380 W Cheyenne Ave Ste 102, Las Vegas, NV 89129
- Hours: Monday to Friday 8:00 AM - 5:00 PM; Saturday and Sunday closed

### Services Offered
- **General Dentistry**: Routine exams, professional cleanings, composite fillings, root canals, crowns, bridges, and dentures.
- **Orthodontics**: Metal braces, ceramic braces, and Invisalign clear aligners for all ages.
- **Pediatric Dentistry**: Comprehensive dental care tailored specifically for children.
- **Cosmetic Dentistry**: Teeth whitening (including Zoom), and porcelain veneers.
- **Oral Surgery & Implants**: Tooth extractions, wisdom teeth removal (with sedation), and permanent dental implants.
- **Emergency Care**: Same-day appointments for dental emergencies (severe toothaches, broken teeth, extractions).

### Handling Inquiries About Services (Crucial Spoken Rule)
- **General Service Inquiries** (e.g., "Tell me about your services", "What services do you offer?", "Aap kya services provide karte hain?", "Tell me about your clinic services"):
  - NEVER read out the full detailed sub-bullet list of procedures at once — it sounds overwhelming and unnatural over the phone.
  - State only the main headings/categories concisely in 1-2 friendly spoken sentences, for example:
    > "We offer General Dentistry, Orthodontics, Pediatric Dentistry, Cosmetic Dentistry, Oral Surgery and Implants, and same-day Emergency Dental Care. Are you interested in a specific service, or would you like to schedule an appointment?"
- **Specific Service Inquiries** (e.g., "What braces do you have?", "Do you do Invisalign?", "Tell me about teeth whitening", "Can I get a dental implant?", "Do you do root canals?"):
  - Provide the specific details for that requested service clearly, then offer to help book a visit:
    > "Yes! For [service], we provide [details from the list above]. Would you like me to help schedule an appointment for that?"

---

## Step 1: Greeting

Greet using the preset message.

<*Wait for patient response*>

---

## Step 2: Identify Patient Intent

Listen to the patient's request and route to the appropriate section:

- Book a new appointment → Step 3
- Reschedule an appointment → Step 4
- Cancel an appointment → Step 5
- General questions or clinic services → Clinic Information & Services Offered section
- Speak to a human → Human Transfer section

---

## Step 3: New Appointment Booking

### 🛑 CRITICAL RULES: MEMORY, DEDUPLICATION, & TOOL EFFICIENCY (READ CAREFULLY!)

1. **NEVER ASK FOR INFORMATION ALREADY PROVIDED**:
   - Always remember every detail the caller has already mentioned earlier in the conversation.
   - If the patient has ALREADY provided any detail (Date, Time, Full Name, Reason for Visit, Date of Birth, Insurance, or Phone Number):
     - **NEVER ASK FOR IT AGAIN!**
     - **IMMEDIATELY SKIP THAT QUESTION and move to the next missing piece of information.**
     - If the caller says "I already told you...", apologize smoothly and acknowledge it: *"My apologies, yes, I have [detail] noted. Let me get your [next missing field]."*

2. **THE TWO APPOINTMENT BOOKING SCENARIOS**:

   - **SCENARIO 1: Caller specifies Date & Time UPFRONT (e.g., in Turn 1: "I want to book an appointment on Wednesday at 2 PM", "Do you have an opening tomorrow at 10 AM?", or mentions both date and time first):**
     1. **Step A**: Call `dental_check_appointment_availability` **ONCE** to verify that requested slot.
     2. **Step B**:
        - **If available (`available: true`)**: immediately confirm availability and ask for the first missing detail:
          > "Great, [Day/Date] at [Time] is available! I'd be happy to schedule that for you. What is your full name?"
        - **If unavailable (`slot_busy` / `available: false`)**:
          - **NEVER use numbered lists (NEVER say "number 1", "number 2", "1.", "2.", "option 1")**.
          - State the date once and offer the alternative times naturally in one conversational sentence:
            > "I'm sorry, [requested time] is not available on [Date], but I do have openings at [Time 1], [Time 2], and [Time 3]. Would any of those times work for you?"
          - <*Wait for patient response*>. Once they choose an opening, lock in that verified slot and proceed to Step D.
     3. **Step C (CRITICAL MEMORY RULE)**:
        - The Date and Time are now **100% LOCKED IN AND VERIFIED**.
        - **NEVER ask for preferred date again! (SKIP Step 3.6 completely!)**
        - **NEVER ask for preferred time again! (SKIP Step 3.7 completely!)**
        - **NEVER call `dental_check_appointment_availability` again in this entire call!**
     4. **Step D**: Collect only the remaining missing details one at a time:
        - Full Name (if not given)
        - Patient Type (New or Existing)
        - Reason for visit
        - Date of Birth
        - Insurance
        - Phone Number
     5. **Step E**: Go directly to Step 3.9 (Confirmation) using the already-verified Date and Time.
     6. **Step F**: When the caller confirms ("Yes", "Looks good", "Confirm"), call `dental-clinic-appointment` directly to finalize booking. (NEVER call availability check again!).

   - **SCENARIO 2: Caller does NOT provide Date & Time upfront (e.g., "I need a cleaning", or provides name/details first):**
     1. Collect initial details one at a time: Full Name, Patient Type, Reason for Visit, Date of Birth, Insurance.
     2. When you reach Date and Time (Step 3.6 & 3.7):
        - Ask: *"What date would you prefer for your appointment?"*
        - Ask: *"What time works best for you? Our hours are Monday through Friday, 8 AM to 5 PM."*
     3. Once the caller provides the desired Date and Time:
        - **Call `dental_check_appointment_availability` ONCE** to verify the slot.
     4. When tool returns available, collect Phone Number (Step 3.8, if not already provided) and proceed to Confirmation (Step 3.9).
     5. When the caller confirms, call `dental-clinic-appointment` directly to finalize booking.

3. **STRICT TOOL CALL FREQUENCY LIMITS**:
   - `dental_check_appointment_availability` must be called **AT MOST ONCE** per requested slot. Never call it multiple times or repeatedly for the same date and time.
   - Once a slot has been checked and verified available in the call, **NEVER check availability again** before booking.
   - When the caller confirms details at Step 3.9, call ONLY `dental-clinic-appointment`. Never call `dental_check_appointment_availability` after caller confirmation.

---

### Information Collection Steps (Only ask if NOT already provided!)

#### Step 3.1: Patient Name *(Skip if already provided)*

Respond with:
> "What is your full name?"
<*Wait for patient response*>
Save the name in UPPERCASE (e.g., "ali muneer" becomes "ALI MUNEER").

#### Step 3.2: Patient Type *(Skip if already provided)*

Respond with:
> "Are you a new or existing patient?"
<*Wait for patient response*>

#### Step 3.3: Reason For Visit *(Skip if already provided)*

Respond with:
> "What brings you in today? Please briefly describe your condition."
<*Wait for patient response*>
Save the answer as `reasonForVisit`. Do not ask the patient to select a service — the backend determines the service from the reason for visit.

#### Step 3.4: Date Of Birth *(Skip if already provided)*

Respond with:
> "What is your date of birth?"
<*Wait for patient response*>
Convert to YYYY-MM-DD.

#### Step 3.5: Insurance *(Skip if already provided)*

Respond with:
> "Do you have dental insurance, or will you be paying out of pocket?"
<*Wait for patient response*>
Save the insurance company name if given, or "Self Pay" / "Not Sure".

#### Step 3.6: Preferred Date *(🛑 SKIP THIS ENTIRELY IF DATE WAS ALREADY GIVEN OR CHECKED IN SCENARIO 1!)*

Only ask if date was NEVER specified by the caller:
> "What date would you prefer for your appointment?"
<*Wait for patient response*>
Convert to YYYY-MM-DD. Never accept a past date.

#### Step 3.7: Preferred Time *(🛑 SKIP THIS ENTIRELY IF TIME WAS ALREADY GIVEN OR CHECKED IN SCENARIO 1!)*

Only ask if time was NEVER specified by the caller:
> "What time works best for you? Our hours are Monday through Friday, 8 AM to 5 PM."
<*Wait for patient response*>
Convert to HH:MM (24-hour). If this is the first time the caller is providing Date & Time (Scenario 2), call `dental_check_appointment_availability` ONCE to verify live calendar status.

#### Step 3.8: Phone Number *(Skip if already provided)*

Respond with:
> "May I have your phone number, please?"
<*Wait for patient response*>

#### Step 3.9: Confirm And Book

Provide a natural variation of:
> "Before I book your appointment, let me confirm the details. Your name is [NAME], your phone number is [PHONE NUMBER], you're visiting for [REASON], your appointment is on [DATE] at [TIME]. Is everything correct?"

Always include the phone number in this confirmation. Do not include the service, insurance, or patient category.
<*Wait for patient response*>

**CRITICAL CONFIRMATION RULES:**
1. DO NOT CALL `dental-clinic-appointment` in the confirmation question turn. You must ONLY recite the summary, ask "Is everything correct?", and wait for the caller's explicit confirmation response.
2. If the patient requests ANY correction (e.g. "change my name to...", "my phone is..."): update the detail and re-confirm without calling the tool.
3. ONLY call `dental-clinic-appointment` in the NEXT turn after the patient explicitly confirms ("Yes", "Correct", "Confirm", "Looks good", etc.).
4. **DO NOT CALL `dental_check_appointment_availability` HERE.** Call ONLY `dental-clinic-appointment`.

Once confirmed, immediately call `dental-clinic-appointment` with:
- `type`: "appointment"
- `callerName`: full name in UPPERCASE
- `phoneNumber`: phone number collected
- `dateOfBirth`: YYYY-MM-DD
- `appointmentDate`: YYYY-MM-DD
- `appointmentTime`: HH:MM (24-hour)
- `insurance`: insurance company name, "Self Pay", or "Not Sure"
- `patientType`: "New Patient" or "Existing Patient"
- `reasonForVisit`: reason described

Never confirm an appointment without calling this tool first, and always wait for its response before telling the patient the outcome.

If the tool response indicates success, immediately provide a natural variation of:
> "Perfect, your appointment is confirmed. You will receive a confirmation message shortly. Is there anything else I can help you with?"
<*Wait for patient response*>

If the tool response indicates the slot is unavailable ("slot_busy") and returns suggested slots:
- **MANDATORY NATURAL SPOKEN RULE (NO NUMBERED LISTS)**:
  - **NEVER say "number 1", "number 2", "option 1", "1.", "2."**.
  - If the suggested slots are on the same date, mention the date once and list the times smoothly together in one natural sentence:
    > "I'm sorry, that specific time is not available on [Date], but we have openings at [Time 1], [Time 2], and [Time 3]. Would any of those times work for you?"
  - If suggested slots span across different dates:
    > "I'm sorry, that time is booked, but we have openings on [Date] at [Times], or on [Next Date] at [Times]. Which of those would you prefer?"
<*Wait for patient response*>

After the patient picks one, keep all previously collected information, update only `appointmentDate` and `appointmentTime`, and immediately call `dental-clinic-appointment` again — do not re-ask for name, phone, reason, date of birth, or insurance. If that call succeeds, provide a natural variation of the success message above.

---

## Step 4: Reschedule Appointment

Collect the following one question at a time.

#### Step 4.1: Patient Name

Respond exactly with:

> "May I have your full name, please?"

<*Wait for patient response*>

Save in UPPERCASE.

#### Step 4.2: Phone Number

Respond exactly with:

> "May I have your phone number, please?"

<*Wait for patient response*>

#### Step 4.3: Current Appointment

Respond exactly with:

> "Please tell me your current appointment date and time."

<*Wait for patient response*>

#### Step 4.4: New Appointment

Respond exactly with:

> "Please tell me your preferred new appointment date and time."

<*Wait for patient response*>

Enforce the same working hours rules as booking.

#### Step 4.5: Confirm And Reschedule

Provide a natural variation of:

> "Current Appointment: Date [DATE], Time [TIME]. Requested Appointment: Date [DATE], Time [TIME]. Is that correct?"

<*Wait for patient response*>

Only after confirmation, immediately call `dental-clinic-appointment` with:

- `type`: "reschedule"
- `callerName`: full name in UPPERCASE
- `phoneNumber`: phone number
- `oldAppointmentDate`: YYYY-MM-DD
- `oldAppointmentTime`: HH:MM (24-hour)
- `newAppointmentDate`: YYYY-MM-DD
- `newAppointmentTime`: HH:MM (24-hour)

Never call the tool before the patient confirms.

**Handling Reschedule Tool Result:**
- If the tool response indicates success:
  Provide a natural variation of:
  > "Your appointment has been successfully rescheduled to [NEW DATE] at [NEW TIME]. You will receive an updated confirmation message shortly. Is there anything else I can help you with?"
- If the tool response indicates "slot_busy" and returns suggested slots:
  - **NEVER say "number 1", "number 2", "option 1", "1.", "2."**.
  - State the date once and offer the alternative times smoothly in one natural sentence:
    > "I'm sorry, that time is not available on [Date], but we have openings at [Time 1], [Time 2], and [Time 3]. Would any of those times work for you?"
- If the tool response indicates an error or that the appointment could not be found:
  NEVER claim the appointment was rescheduled. Honestly inform the patient:
  > "I'm sorry, I wasn't able to find an active appointment under that name and phone number to reschedule. Could you please double-check the registered name and phone number used when booking?"

---

## Step 5: Cancel Appointment

#### Step 5.1: Confirm Identity

Respond exactly with:

> "May I have your full name, please?"

<*Wait for patient response*>

Save in UPPERCASE.

Respond exactly with:

> "May I have your phone number, please?"

<*Wait for patient response*>

#### Step 5.2: Cancel

Immediately call `dental-clinic-appointment` with:

- `type`: "cancel"
- `callerName`: full name in UPPERCASE
- `phoneNumber`: phone number

**Handling Cancel Tool Result:**
- If the tool response indicates success:
  Provide a natural variation of:
  > "Your appointment has been successfully cancelled. Is there anything else I can help you with?"
- If the tool response indicates an error or that the appointment could not be found:
  NEVER claim the appointment was cancelled. Honestly inform the patient:
  > "I'm sorry, I wasn't able to find an active appointment under that name and phone number to cancel. Could you please double-check the registered name and phone number?"

<*Wait for patient response*>

---

## Human Transfer

If the patient insists on speaking to a human, provide a natural variation of:

> "Of course. Let me transfer you to our front desk team right away. Please hold."

Call `transfer_call` to connect to the front desk.

---

## Guardrails

Only discuss dental clinic-related topics (including clinic hours, location, services offered, dental procedures, current clinic date and time, and dental appointments).

If asked about unrelated topics, other clinics, or competitors, provide a natural variation of:

> "I can only assist with dental appointments, our clinic services, and office information."

If asked for medical or dental diagnoses or treatment advice, provide a natural variation of:

> "For medical advice, please consult with the dentist during your appointment."

If asked about specific billing amounts, provide a natural variation of:

> "For billing details, our team will assist you during your visit."

---

## Natural Spoken Pronunciation (Voice Guideline)
Everything you speak will be converted into spoken audio:
- Never speak raw ISO dates like '2026-09-22'. Speak natural dates like 'September 22nd' or 'Tuesday, September 22nd'.
- Never speak 24-hour military times or colons like '11:00' or '11:00 AM'. Always speak '11 AM', '9 AM', '2:30 PM', or 'eleven AM'.

---

## General Guidelines

- Keep answers to 2-3 sentences maximum for general questions.
- Always collect only one piece of information at a time unless specifically instructed otherwise.
- Always convert dates to YYYY-MM-DD and times to HH:MM (24-hour) before calling `dental-clinic-appointment` or `dental_check_appointment_availability`.
- Do not repeatedly ask for information the patient already provided.
- Always execute `dental_check_appointment_availability` to verify slot status whenever a caller asks if a slot is open. Never assume availability.
- Always wait for tool responses before making claims about availability, booking, rescheduling, or cancellation.

---

## Hold Handling

If the patient says "Hold on," "One moment," "Please wait" (or in Spanish, "Espera," "Un momento"), respond exactly with:

NO_RESPONSE_NEEDED
"""


def extract_conversational_chunk(buffer: str, is_initial_turn_chunk: bool = False):
    """
    Extracts conversational speech phrases for low-latency streaming TTS (Retell AI architecture).
    
    1. Primary phrase boundaries (. ? ! \\n):
       Splits immediately whenever a sentence ends.
    2. Conversational pauses (, ; : - —):
       Splits at commas/semicolons if the phrase has sufficient context:
       - First chunk of a turn: >= 14 chars (or >= 3 words) for instant first-sound response (<300ms)
       - Subsequent chunks: >= 24 chars (or >= 4 words)
    3. Safety length cap:
       If no punctuation appears within 45 chars (initial) or 75 chars (subsequent),
       splits at the last space to avoid speech latency stalls.
    """
    if not buffer:
        return None, buffer

    primary_punct = [".", "?", "!", "\n"]
    secondary_punct = [",", ";", ":", "—", " - "]

    # 1. Primary sentence boundaries: split immediately
    earliest_p = None
    for p in primary_punct:
        pos = buffer.find(p)
        if pos != -1 and (earliest_p is None or pos < earliest_p):
            earliest_p = pos
    if earliest_p is not None:
        chunk = buffer[:earliest_p + 1].strip()
        remaining = buffer[earliest_p + 1:]
        return chunk, remaining

    # 2. Secondary conversational boundaries: split if min length reached
    min_len = 14 if is_initial_turn_chunk else 24
    earliest_s = None
    for p in secondary_punct:
        search_start = 0
        while True:
            pos = buffer.find(p, search_start)
            if pos == -1:
                break
            # Guard against time colons like 2:00 or 6:56
            if p == ":":
                is_time_colon = (
                    pos > 0 and pos < len(buffer) - 1 and
                    buffer[pos - 1].isdigit() and buffer[pos + 1].isdigit()
                )
                if is_time_colon:
                    search_start = pos + 1
                    continue
            if pos >= min_len and (earliest_s is None or pos < earliest_s):
                earliest_s = pos
            break
    if earliest_s is not None:
        chunk = buffer[:earliest_s + 1].strip()
        remaining = buffer[earliest_s + 1:]
        return chunk, remaining

    # 3. Safety cap: break at nearest word boundary
    max_len = 45 if is_initial_turn_chunk else 75
    if len(buffer) >= max_len:
        cut = buffer.rfind(" ", 0, max_len)
        if cut >= min_len:
            # Prevent cutting between a time and its AM/PM marker (e.g. "2" and "PM" or "6:56" and "PM")
            after_cut = buffer[cut:].lstrip()
            ampm_match = re.match(r'^(?:am|pm|a\.m\.|p\.m\.)\b', after_cut, flags=re.IGNORECASE)
            if ampm_match:
                advance = buffer[cut:].find(after_cut) + ampm_match.end()
                cut += advance
            return buffer[:cut].strip(), buffer[cut:].lstrip()

    return None, buffer


# Backwards compatibility alias
extract_complete_sentence = extract_conversational_chunk


class BrowserVoiceSession:
    """Manages an active browser voice session over WebSocket."""

    def __init__(self, client_ws):
        self.client_ws = client_ws
        self.openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self.openai_sync_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
        self.http_client = httpx.AsyncClient(timeout=15.0)
        self.cartesia_client = Cartesia(api_key=CARTESIA_API_KEY) if CARTESIA_API_KEY else None
        self.deepgram_tts: Optional[DeepgramTTSWebSocketSession] = None
        if ELEVENLABS_API_KEY:
            try:
                self.elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            except Exception:
                self.elevenlabs_client = None
        else:
            self.elevenlabs_client = None
        self.call_start_time = datetime.now()
        self.call_start_perf = time.perf_counter()
        self.completed_tool_calls: List[Dict[str, Any]] = []
        self.checked_availability_slots: set = set()
        self.conversation_history = [
            {"role": "assistant", "content": GREETING_TEXT}
        ]
        self.stop_event = asyncio.Event()
        self.tts_stop_event = asyncio.Event()
        self.active_response_task = None
        self.last_processed_transcript = ""
        self.last_processed_time = 0.0
        self.duplicate_window = 2.0
        self.is_speaking = False
        self.audio_playback_end_time = 0.0
        self.current_speaking_text = ""
        self.greeting_in_progress = False

    def is_speaking_now(self) -> bool:
        """Accurately checks whether Sophia is currently generating or actively playing audio in the browser."""
        return self.is_speaking and (time.perf_counter() < self.audio_playback_end_time + 0.15)

    def is_valid_barge_in(self, transcript: str) -> bool:
        """
        Determines whether a partial or final transcript represents a genuine human interruption.
        Prevents false interruptions caused by:
        1. Microphone static, noise, clicks, or coughs (e.g. '***', 'um', 'ah').
        2. Acoustic speaker echo (when Sophia's own voice leaks from laptop speakers into the mic).
        3. Initial connection noise during the welcome greeting.
        """
        if not self.is_speaking_now():
            return False

        # Clean transcript: remove asterisks, punctuation, and extra whitespace
        cleaned = re.sub(r'[\*\.,\?!;:_\-]+', ' ', transcript).strip()
        if not cleaned:
            return False

        # Extract alphanumeric words
        words = [w.lower() for w in re.findall(r'[a-zA-Z0-9]+', cleaned)]
        if not words:
            return False

        # Filter out common non-committal filler sounds
        meaningful_words = [w for w in words if w not in ("uh", "um", "ah", "eh", "er", "mm")]
        if not meaningful_words:
            return False

        # Explicit immediate interruption keywords that can trigger with a single word
        INTERRUPT_KEYWORDS = {
            "stop", "wait", "hold", "pause", "listen", "no", "cancel",
            "ruko", "suno", "chup", "thairo", "ruk", "rok"
        }

        # Check if caller spoke an explicit single-word command
        if len(meaningful_words) == 1:
            if meaningful_words[0] in INTERRUPT_KEYWORDS:
                return True
            # Single random words that are not explicit commands are almost always noise/echo
            return False

        # Check for acoustic echo from Sophia's own voice
        # If >= 70% of words match what Sophia is currently speaking, it's echo from the speakers
        if self.current_speaking_text:
            speaking_words = set(re.findall(r'[a-zA-Z0-9]+', self.current_speaking_text.lower()))
            echo_matches = sum(1 for w in meaningful_words if w in speaking_words)
            echo_ratio = echo_matches / len(meaningful_words)
            if echo_ratio >= 0.70:
                print(f"[Acoustic Echo Ignored] Transcript '{transcript}' matches {echo_ratio*100:.0f}% of Sophia's speech.")
                return False

        # Welcome greeting protection:
        # During the first welcome greeting, require at least 3 meaningful words (or an explicit interrupt keyword)
        # to prevent initial connection/mic clicks from cutting off Sophia's greeting.
        if self.greeting_in_progress:
            if len(meaningful_words) < 3 and not any(w in INTERRUPT_KEYWORDS for w in meaningful_words):
                return False

        # Minimum threshold for interruption: at least 2 meaningful words or length >= 8
        return len(meaningful_words) >= 2 or len(cleaned) >= 8

    async def send_to_client(self, message: dict):
        """Helper to send JSON events to the browser client."""
        try:
            await self.client_ws.send_text(json.dumps(message))
        except Exception:
            pass

    async def _stream_pcm_data(self, pcm_bytes: bytes, frame_size: int = 9600):
        """
        Streams raw 24kHz linear16 PCM audio to browser client in solid,
        smooth 200ms frames (9600 bytes = 200ms @ 24kHz mono).
        Prevents buffer underruns, syllable cuts, and audio stuttering.
        """
        if not pcm_bytes:
            return
        offset = 0
        total = len(pcm_bytes)
        while offset < total:
            if self.tts_stop_event.is_set():
                break
            end = min(offset + frame_size, total)
            chunk = pcm_bytes[offset:end]
            offset = end

            chunk_sec = len(chunk) / 48000.0
            self.audio_playback_end_time = max(time.perf_counter(), self.audio_playback_end_time) + chunk_sec
            self.is_speaking = True

            b64_audio = base64.b64encode(chunk).decode("utf-8")
            await self.send_to_client({
                "type": "assistant_audio",
                "audio": b64_audio,
                "sample_rate": 24000,
            })
            await asyncio.sleep(0.01)

    async def speak_text(self, text: str):
        """
        Generates high-speed studio TTS audio and streams smooth 200ms frames to browser asynchronously.
        Multi-tier provider priority:
        1. Cartesia Sonic-2 (ultra-low latency, 3.3x realtime)
        2. OpenAI tts-1 (rock solid, 1.2x realtime)
        3. ElevenLabs Flash v2.5
        4. Deepgram REST
        """
        if not text.strip():
            return
        if self.tts_stop_event.is_set():
            return
        self.is_speaking = True
        cleaned_text = clean_text_for_speech(text)
        self.current_speaking_text = cleaned_text
        start_t = time.perf_counter()

        # 1. Primary: Cartesia Sonic-2
        if self.cartesia_client and not self.tts_stop_event.is_set():
            try:
                loop = asyncio.get_running_loop()
                def run_cartesia():
                    resp = self.cartesia_client.tts.generate(
                        model_id=CARTESIA_MODEL_ID,
                        transcript=cleaned_text,
                        voice={"mode": "id", "id": CARTESIA_VOICE_ID},
                        output_format={"container": "raw", "encoding": "pcm_s16le", "sample_rate": 24000},
                    )
                    return resp.read()

                audio_data = await loop.run_in_executor(None, run_cartesia)
                if audio_data and not self.tts_stop_event.is_set():
                    dur = time.perf_counter() - start_t
                    audio_dur = len(audio_data) / 48000.0
                    print(f"[TTS Cartesia] Generated {audio_dur:.2f}s audio in {dur*1000:.0f}ms (Speed: {audio_dur/max(0.001, dur):.1f}x)")
                    await self._stream_pcm_data(audio_data)
                    return
            except Exception as e:
                print(f"[TTS Cartesia Error, falling back to OpenAI] {e}")

        # 2. Fallback 1: OpenAI tts-1 (shimmer voice, 24kHz PCM)
        if self.openai_sync_client and not self.tts_stop_event.is_set():
            try:
                loop = asyncio.get_running_loop()
                def run_openai():
                    resp = self.openai_sync_client.audio.speech.create(
                        model="tts-1",
                        voice="shimmer",
                        response_format="pcm",
                        input=cleaned_text,
                    )
                    return resp.read()

                audio_data = await loop.run_in_executor(None, run_openai)
                if audio_data and not self.tts_stop_event.is_set():
                    dur = time.perf_counter() - start_t
                    audio_dur = len(audio_data) / 48000.0
                    print(f"[TTS OpenAI] Generated {audio_dur:.2f}s audio in {dur*1000:.0f}ms")
                    await self._stream_pcm_data(audio_data)
                    return
            except Exception as e:
                print(f"[TTS OpenAI Error, falling back to ElevenLabs] {e}")

        # 3. Fallback 2: ElevenLabs Flash v2.5
        if self.elevenlabs_client and not self.tts_stop_event.is_set():
            try:
                loop = asyncio.get_running_loop()
                def run_elevenlabs():
                    stream = self.elevenlabs_client.text_to_speech.stream(
                        voice_id=TTS_VOICE,
                        output_format="pcm_24000",
                        text=cleaned_text,
                        model_id=TTS_MODEL,
                    )
                    return b"".join(stream)

                audio_data = await loop.run_in_executor(None, run_elevenlabs)
                if audio_data and not self.tts_stop_event.is_set():
                    dur = time.perf_counter() - start_t
                    audio_dur = len(audio_data) / 48000.0
                    print(f"[TTS ElevenLabs] Generated {audio_dur:.2f}s audio in {dur*1000:.0f}ms")
                    await self._stream_pcm_data(audio_data)
                    return
            except Exception as e:
                print(f"[TTS ElevenLabs Error, falling back to Deepgram] {e}")

        # 4. Fallback 3: Deepgram REST
        if DEEPGRAM_API_KEY and not self.tts_stop_event.is_set():
            print(f"[TTS Fallback: Deepgram REST] Generating speech for: '{cleaned_text[:60]}...'")
            try:
                url = "https://api.deepgram.com/v1/speak"
                headers = {
                    "Authorization": f"Token {DEEPGRAM_API_KEY}",
                    "Content-Type": "application/json",
                }
                params = {
                    "model": DEEPGRAM_TTS_MODEL,
                    "encoding": "linear16",
                    "sample_rate": 24000,
                    "container": "none",
                }
                payload = {"text": cleaned_text}

                resp = await self.http_client.post(url, headers=headers, params=params, json=payload)
                if resp.status_code == 200 and not self.tts_stop_event.is_set():
                    await self._stream_pcm_data(resp.content)
                    return
            except Exception as e:
                print(f"[TTS Deepgram REST Error] {e}")
        self.is_speaking = False

    async def process_user_turn(self, user_text: str):
        """Processes a finalized user turn through streaming OpenAI and Cartesia/OpenAI TTS."""
        if not user_text.strip():
            return

        self.conversation_history.append({"role": "user", "content": user_text})
        # Keep full conversation history for the current call session (generous safety cap of 50 messages)
        history_to_send = self.conversation_history[-50:] if len(self.conversation_history) > 50 else self.conversation_history
        print(f"[DEBUG] Conversation history messages sent to OpenAI: {len(history_to_send)} (Total session: {len(self.conversation_history)})")

        messages = [{"role": "system", "content": build_system_prompt()}]
        messages.extend(history_to_send)

        sentence_queue = asyncio.Queue()

        async def tts_worker():
            while True:
                sentence = await sentence_queue.get()
                if sentence is None:
                    break
                if not sentence.strip() or self.tts_stop_event.is_set():
                    continue
                await self.speak_text(sentence)
                if self.tts_stop_event.is_set():
                    break

        tts_task = asyncio.create_task(tts_worker())

        async def dispatch_tts_chunk(chunk_text: str):
            if not chunk_text.strip() or self.tts_stop_event.is_set():
                return
            cleaned = clean_text_for_speech(chunk_text)
            if not cleaned:
                return
            await sentence_queue.put(cleaned)

        async def finish_tts_turn(rem_buf: str = ""):
            if rem_buf.strip() and not self.tts_stop_event.is_set():
                cleaned = clean_text_for_speech(rem_buf)
                if cleaned:
                    await sentence_queue.put(cleaned)
            await sentence_queue.put(None)
            if tts_task:
                await tts_task

        self.current_speaking_text = ""
        try:
            stream = await self.openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                tools=APPOINTMENT_TOOLS,
                tool_choice="auto",
                temperature=0.2,
                max_tokens=120,
                stream=True,
            )

            full_response = ""
            buffer = ""
            tool_calls_dict = {}
            has_started_text = False
            is_initial_turn_chunk = True

            async for chunk in stream:
                if self.tts_stop_event.is_set():
                    break
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta

                # Accumulate tool calls if present
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_dict:
                            tool_calls_dict[idx] = {
                                "id": tc_delta.id or "",
                                "name": tc_delta.function.name if (tc_delta.function and tc_delta.function.name) else "",
                                "arguments": "",
                            }
                        if tc_delta.id:
                            tool_calls_dict[idx]["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_calls_dict[idx]["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_calls_dict[idx]["arguments"] += tc_delta.function.arguments

                # Accumulate and stream text content if present
                if delta.content:
                    if not has_started_text:
                        has_started_text = True
                        await self.send_to_client({"type": "assistant_text_start"})

                    full_response += delta.content
                    buffer += delta.content

                    # Stream each delta progressively to the browser immediately
                    await self.send_to_client({
                        "type": "assistant_text_delta",
                        "text": delta.content,
                    })

                    # Extract conversational chunks and dispatch to TTS with zero delay
                    while True:
                        phrase, remaining = extract_conversational_chunk(
                            buffer, is_initial_turn_chunk=is_initial_turn_chunk
                        )
                        if phrase:
                            await dispatch_tts_chunk(phrase)
                            buffer = remaining
                            is_initial_turn_chunk = False
                            continue
                        break

            # Handle Tool Calls if any were triggered
            if tool_calls_dict and not self.tts_stop_event.is_set():
                formatted_tool_calls = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"],
                        },
                    }
                    for tc in tool_calls_dict.values()
                ]

                # Flush any introductory text spoken before the tool execution
                if buffer.strip():
                    await dispatch_tts_chunk(buffer.strip())
                    buffer = ""

                # If introductory text was streamed before tool calls, close that bubble first
                if has_started_text:
                    await self.send_to_client({"type": "assistant_text_end"})
                    has_started_text = False

                for tc in formatted_tool_calls:
                    print(f"[TOOL] OpenAI requested: {tc['function']['name']}")
                    print(f"[TOOL] Arguments: {tc['function']['arguments']}")

                # 1. Talk While Waiting (Silence Breaker / Retell AI Execution Feedback)
                # If OpenAI did not stream any introductory phrase before deciding to call the tool,
                # speak an immediate, natural filler phrase so the caller never hears awkward silence.
                if not full_response.strip():
                    primary_tool = formatted_tool_calls[0]["function"]["name"]
                    try:
                        primary_args = json.loads(formatted_tool_calls[0]["function"]["arguments"])
                    except Exception:
                        primary_args = {}

                    if primary_tool in ("dental_check_appointment_availability", "check_appointment_availability"):
                        waiting_phrase = "One moment, let me check our schedule for you."
                    elif primary_tool in ("dental-clinic-appointment", "dental_clinic_appointment", "clinicappointment"):
                        action_type = primary_args.get("type", "appointment").lower()
                        if action_type == "appointment":
                            waiting_phrase = "Alright, let me get that booked for you."
                        elif action_type == "reschedule":
                            waiting_phrase = "One moment, let me update your appointment."
                        elif action_type == "cancel":
                            waiting_phrase = "One moment, let me cancel that for you."
                        else:
                            waiting_phrase = "One moment while I process that for you."
                    else:
                        waiting_phrase = "One moment, please."

                    # Send waiting phrase to frontend UI and queue for TTS audio immediately
                    await self.send_to_client({"type": "assistant_text_start"})
                    await self.send_to_client({"type": "assistant_text_delta", "text": waiting_phrase})
                    await self.send_to_client({"type": "assistant_text_end"})
                    await sentence_queue.put(waiting_phrase)
                    full_response = waiting_phrase

                # Append assistant tool calls to message history
                messages.append({
                    "role": "assistant",
                    "content": full_response if full_response else None,
                    "tool_calls": formatted_tool_calls,
                })

                # Execute each tool call
                for tc in formatted_tool_calls:
                    call_id = tc["id"]
                    fn_name = tc["function"]["name"]
                    fn_args_str = tc["function"]["arguments"]

                    try:
                        args = json.loads(fn_args_str)
                    except json.JSONDecodeError:
                        args = {}

                    # Notify frontend that tool call started
                    await self.send_to_client({
                        "type": "tool_call_start",
                        "tool_name": fn_name,
                        "tool_call_id": call_id,
                        "arguments": args,
                    })

                    async def run_tool():
                        if fn_name in ("dental_check_appointment_availability", "check_appointment_availability"):
                            req_date = str(args.get("appointmentDate", "")).strip()
                            req_time = str(args.get("appointmentTime", "")).strip()
                            slot_key = f"{req_date}_{req_time}"

                            if slot_key and slot_key in self.checked_availability_slots:
                                print(f"[TOOL Guard] Slot '{slot_key}' was already verified available in this session. Suppressing redundant n8n call.")
                                return {
                                    "status": "available",
                                    "available": True,
                                    "appointmentDate": req_date,
                                    "appointmentTime": req_time,
                                    "message": f"Slot on {req_date} at {req_time} is verified available.",
                                }

                            print(f"[TOOL] Sending dental_check_appointment_availability request to n8n")
                            res = await dental_check_appointment_availability(
                                appointmentDate=args.get("appointmentDate", ""),
                                appointmentTime=args.get("appointmentTime", ""),
                                type=args.get("type", "availability"),
                            )
                            if res.get("available") is True or res.get("status") == "available":
                                self.checked_availability_slots.add(slot_key)
                            return res
                        elif fn_name in ("dental-clinic-appointment", "dental_clinic_appointment", "clinicappointment"):
                            # Defensive guard: if the assistant emitted text asking for confirmation in this same turn,
                            # do not dispatch dental-clinic-appointment now; wait for caller's explicit confirmation response.
                            is_asking_confirmation = False
                            if full_response:
                                lower_text = full_response.lower()
                                if any(q in lower_text for q in ["is everything correct", "is that correct", "confirm the details", "does that look good", "is that right"]):
                                    is_asking_confirmation = True

                            if is_asking_confirmation:
                                print(f"[TOOL Guard] Suppressed premature dental-clinic-appointment because assistant is asking for confirmation.")
                                return {
                                    "status": "pending_confirmation",
                                    "message": "The assistant asked the caller to confirm the appointment details. Waiting for caller's confirmation response before booking.",
                                }
                            else:
                                print(f"[TOOL] Sending dental-clinic-appointment request to n8n")
                                return await dental_clinic_appointment(
                                    type=args.get("type", ""),
                                    callerName=args.get("callerName", ""),
                                    phoneNumber=args.get("phoneNumber", ""),
                                    appointmentDate=args.get("appointmentDate"),
                                    appointmentTime=args.get("appointmentTime"),
                                    dateOfBirth=args.get("dateOfBirth"),
                                    patientType=args.get("patientType"),
                                    reasonForVisit=args.get("reasonForVisit"),
                                    insurance=args.get("insurance"),
                                    oldAppointmentDate=args.get("oldAppointmentDate"),
                                    oldAppointmentTime=args.get("oldAppointmentTime"),
                                    newAppointmentDate=args.get("newAppointmentDate"),
                                    newAppointmentTime=args.get("newAppointmentTime"),
                                )
                        else:
                            return {"error": f"Unknown tool: {fn_name}"}

                    tool_task = asyncio.create_task(run_tool())
                    try:
                        done, _ = await asyncio.wait([tool_task], timeout=3.0)
                        if not done and not self.tts_stop_event.is_set():
                            long_wait_phrase = "Thank you for your patience, just a moment..."
                            print(f"[TOOL Watchdog] Tool execution exceeded 3s; speaking reassurance: '{long_wait_phrase}'")
                            await self.send_to_client({"type": "assistant_text_start"})
                            await self.send_to_client({"type": "assistant_text_delta", "text": long_wait_phrase})
                            await self.send_to_client({"type": "assistant_text_end"})
                            await sentence_queue.put(long_wait_phrase)
                            tool_result = await tool_task
                        else:
                            tool_result = tool_task.result()
                    except Exception as ex:
                        print(f"[TOOL Execution Error] {ex}")
                        tool_result = {"status": "error", "error": str(ex)}

                    # Determine success for UI
                    is_success = not bool(
                        tool_result.get("error") or
                        tool_result.get("status") == "error"
                    )

                    # Notify frontend with tool call result
                    await self.send_to_client({
                        "type": "tool_call_result",
                        "tool_name": fn_name,
                        "tool_call_id": call_id,
                        "result": tool_result,
                        "success": is_success,
                    })

                    # Safely track completed tool call for CRM session logging
                    if hasattr(self, "completed_tool_calls"):
                        self.completed_tool_calls.append({
                            "name": fn_name,
                            "arguments": args,
                            "result": tool_result,
                            "success": is_success,
                        })
                    try:
                        from backend.crm.crm_service import log_appointment_action_background
                        asyncio.create_task(log_appointment_action_background(fn_name, args, tool_result, is_success))
                    except Exception as _crm_action_err:
                        pass

                    print(f"[TOOL] Tool result returned to OpenAI: {tool_result}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": fn_name,
                        "content": json.dumps(tool_result),
                    })

                # Second OpenAI stream call with the tool results
                second_stream = await self.openai_client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=120,
                    stream=True,
                )

                if not has_started_text:
                    has_started_text = True
                    await self.send_to_client({"type": "assistant_text_start"})

                is_initial_turn_chunk = True
                async for chunk in second_stream:
                    if self.tts_stop_event.is_set():
                        break
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if not delta.content:
                        continue

                    full_response += delta.content
                    buffer += delta.content

                    await self.send_to_client({
                        "type": "assistant_text_delta",
                        "text": delta.content,
                    })

                    while True:
                        phrase, remaining = extract_conversational_chunk(
                            buffer, is_initial_turn_chunk=is_initial_turn_chunk
                        )
                        if phrase:
                            await dispatch_tts_chunk(phrase)
                            buffer = remaining
                            is_initial_turn_chunk = False
                            continue
                        break

                # Finish remaining speech after tool result
                await finish_tts_turn(buffer)
                buffer = ""

            else:
                # No tools called; finish speech from first stream
                await finish_tts_turn(buffer)
                buffer = ""

            # Signal end of text streaming to client immediately
            if has_started_text:
                await self.send_to_client({"type": "assistant_text_end"})

            if full_response.strip():
                self.conversation_history.append({"role": "assistant", "content": full_response.strip()})

        except asyncio.CancelledError:
            await sentence_queue.put(None)
            await self.send_to_client({"type": "assistant_text_end"})
        except Exception as e:
            await sentence_queue.put(None)
            print(f"[OpenAI Streaming Error] {e}")
            await self.send_to_client({
                "type": "error",
                "message": f"AI streaming error: {str(e)}",
            })

    async def run(self):
        """Main lifecycle of the browser session."""
        if not ASSEMBLYAI_API_KEY or not OPENAI_API_KEY or not (DEEPGRAM_API_KEY or ELEVENLABS_API_KEY):
            await self.send_to_client({
                "type": "error",
                "message": "Missing required API keys in backend .env file.",
            })
            return

        params = {
            "sample_rate": SAMPLE_RATE,
            "speech_model": "universal-3-5-pro",
            "min_turn_silence": 300,
            "end_of_turn_confidence_threshold": 0.5,
        }
        url = f"{ASSEMBLYAI_WS}?{urlencode(params)}"


        try:
            async with websockets.connect(
                url,
                additional_headers={"Authorization": ASSEMBLYAI_API_KEY},
            ) as assemblyai_ws:
                print("[AssemblyAI] Browser voice session connected to streaming STT.")
                await self.send_to_client({
                    "type": "connection_status",
                    "status": "connected",
                })

                audio_queue = asyncio.Queue()
                recv_chunk_count = 0
                fwd_chunk_count = 0

                async def monitor_event_loop():
                    """Monitors if the asyncio event loop gets blocked by synchronous I/O."""
                    while not self.stop_event.is_set():
                        t0 = time.perf_counter()
                        await asyncio.sleep(0.05)
                        dt = time.perf_counter() - t0
                        if dt > 0.15:  # Expected 50ms, took >150ms
                            print(f"[DIAGNOSTIC WARNING] Event loop blocked for {dt*1000:.0f}ms!")

                async def forward_audio():
                    """Reads raw binary PCM from browser and sends to AssemblyAI."""
                    nonlocal fwd_chunk_count
                    try:
                        while not self.stop_event.is_set():
                            data = await audio_queue.get()
                            if data is None:
                                break
                            fwd_chunk_count += 1
                            if fwd_chunk_count % 25 == 1:
                                print(f"[AssemblyAI Forward] Forwarding chunk #{fwd_chunk_count} ({len(data)} bytes) to AssemblyAI")
                            await assemblyai_ws.send(data)
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        print(f"[Audio Forward Error] {e}")

                async def receive_from_assemblyai():
                    """Listens for transcripts from AssemblyAI and routes them."""
                    try:
                        async for raw_message in assemblyai_ws:
                            if self.stop_event.is_set():
                                break
                            try:
                                message = json.loads(raw_message)
                            except json.JSONDecodeError:
                                continue

                            event_type = message.get("type")

                            if event_type == "Begin":
                                print("[AssemblyAI Event] Begin - starting welcome greeting.")
                                # Play Sophia's initial greeting with greeting protection enabled
                                self.tts_stop_event.clear()
                                self.greeting_in_progress = True
                                self.current_speaking_text = GREETING_TEXT
                                await self.send_to_client({"type": "assistant_text_start"})
                                await self.send_to_client({
                                    "type": "assistant_text_delta",
                                    "text": GREETING_TEXT,
                                })
                                await self.send_to_client({"type": "assistant_text_end"})
                                if GREETING_PCM_BYTES:
                                    print(f"[Greeting Audio] Instantly streaming pre-cached studio greeting ({len(GREETING_PCM_BYTES)} bytes, 0ms latency)")
                                    asyncio.create_task(self._stream_pcm_data(GREETING_PCM_BYTES))
                                else:
                                    asyncio.create_task(self.speak_text(GREETING_TEXT))

                            elif event_type == "Turn":
                                transcript = message.get("transcript", "").strip()
                                end_of_turn = message.get("end_of_turn", False)

                                if not transcript:
                                    continue

                                try:
                                    print(f"[AssemblyAI Turn] end_of_turn={end_of_turn}, text={repr(transcript)}")
                                except Exception:
                                    pass

                                if not end_of_turn:
                                    # Partial transcript: filter out pure asterisks or noise symbols
                                    clean_partial = re.sub(r'[\*\.,\?!;:_\-]+', ' ', transcript).strip()
                                    if clean_partial:
                                        await self.send_to_client({
                                            "type": "user_transcript",
                                            "text": transcript,
                                            "final": False,
                                        })

                                    # Intelligent Barge-in with Acoustic Echo Cancellation & Noise Shielding
                                    if self.is_valid_barge_in(transcript):
                                        print(f"[Barge-in Triggered] Valid human interruption by caller: '{transcript}'")
                                        self.tts_stop_event.set()
                                        self.is_speaking = False
                                        self.audio_playback_end_time = 0.0
                                        self.greeting_in_progress = False
                                        if self.deepgram_tts and self.deepgram_tts.is_connected:
                                            await self.deepgram_tts.clear()
                                        if self.active_response_task and not self.active_response_task.done():
                                            self.active_response_task.cancel()
                                        await self.send_to_client({
                                            "type": "interrupted",
                                        })
                                else:
                                    # Final transcript: when user completes their turn, greeting is done
                                    self.greeting_in_progress = False

                                    # Filter noise on final transcript (e.g. '***' or empty punctuation)
                                    clean_final = re.sub(r'[\*\.,\?!;:_\-]+', ' ', transcript).strip()
                                    if not clean_final:
                                        print(f"[AssemblyAI Turn] Ignored empty/noise final transcript: {repr(transcript)}")
                                        continue

                                    current_time = time.perf_counter()
                                    same_transcript = transcript.lower() == self.last_processed_transcript.lower()
                                    too_soon = (current_time - self.last_processed_time) < self.duplicate_window

                                    if same_transcript and too_soon:
                                        print(f"[Duplicate Ignored] '{transcript}' within {self.duplicate_window}s")
                                        continue

                                    self.last_processed_transcript = transcript
                                    self.last_processed_time = current_time

                                    await self.send_to_client({
                                        "type": "user_transcript",
                                        "text": transcript,
                                        "final": True,
                                    })

                                    if self.active_response_task and not self.active_response_task.done():
                                        self.active_response_task.cancel()

                                    self.tts_stop_event.clear()
                                    if self.deepgram_tts and self.deepgram_tts.is_connected:
                                        await self.deepgram_tts.clear()
                                    self.active_response_task = asyncio.create_task(
                                        self.process_user_turn(transcript)
                                    )

                            elif event_type == "Termination":
                                print("[AssemblyAI Event] Termination")
                                break
                            elif event_type == "Error":
                                err_msg = message.get("error", "AssemblyAI STT error")
                                print(f"[AssemblyAI STT Error] {err_msg}")
                                await self.send_to_client({
                                    "type": "error",
                                    "message": f"STT error: {err_msg}",
                                 })
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        print(f"[AssemblyAI Receive Error] {e}")

                loop_monitor_task = asyncio.create_task(monitor_event_loop())
                forward_task = asyncio.create_task(forward_audio())
                receive_task = asyncio.create_task(receive_from_assemblyai())

                # Loop to receive audio messages from the browser client
                try:
                    while not self.stop_event.is_set():
                        message = await self.client_ws.receive()
                        if "bytes" in message and message["bytes"]:
                            # Binary PCM audio chunk from browser microphone
                            recv_chunk_count += 1
                            if recv_chunk_count % 25 == 1:
                                print(f"[Browser Mic In] Received chunk #{recv_chunk_count} ({len(message['bytes'])} bytes) from browser")
                            await audio_queue.put(message["bytes"])
                        elif "text" in message and message["text"]:
                            # JSON control messages (e.g. stop/end call)
                            try:
                                payload = json.loads(message["text"])
                                if payload.get("type") == "stop":
                                    print("[Browser WS] Received stop command")
                                    break
                            except json.JSONDecodeError:
                                pass
                        elif message.get("type") == "websocket.disconnect":
                            print("[Browser WS] Client disconnected")
                            break
                finally:
                    self.stop_event.set()
                    self.tts_stop_event.set()
                    loop_monitor_task.cancel()
                    if self.deepgram_tts:
                        try:
                            await self.deepgram_tts.close()
                        except Exception:
                            pass
                    await audio_queue.put(None)
                    forward_task.cancel()
                    receive_task.cancel()
                    if self.active_response_task and not self.active_response_task.done():
                        self.active_response_task.cancel()
                    try:
                        await assemblyai_ws.send(json.dumps({"type": "Terminate"}))
                    except Exception:
                        pass
                    try:
                        await self.http_client.aclose()
                    except Exception:
                        pass
                    # Safely record completed call session into CRM database in background
                    try:
                        from backend.crm.crm_service import log_voice_session_background
                        asyncio.create_task(log_voice_session_background(self))
                    except Exception as _crm_log_err:
                        print(f"[CRM Voice Hook Warning] Could not log voice session: {_crm_log_err}")

        except Exception as e:
            print(f"[BrowserVoiceSession Error] {e}")
            await self.send_to_client({
                "type": "error",
                "message": f"Connection error: {str(e)}",
            })
