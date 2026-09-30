# CareVoice AI 🎙️🦷
### Autonomous Dental Clinic Voice Receptionist & Real-Time Operational CRM

> **CareVoice AI** is an intelligent, ultra-low latency healthcare voice AI receptionist and clinical management system built for dental practices. Powered by **AssemblyAI Streaming WebSocket STT**, **Cartesia Sonic-2 Voice Synthesis**, **OpenAI GPT-4o-mini**, and an end-to-end automated **n8n Webhook, Google Calendar, Google Sheets & WhatsApp Notification Pipeline**, accompanied by a full-fledged **Dental Practice CRM & Admin Dashboard**.

---

## 🌟 Executive Summary & Problem Solved

Dental clinics and specialty practices lose over **30% of incoming patient bookings** due to missed calls after hours, staff overload during peak clinical procedures, and friction in scheduling. 

**CareVoice AI** acts as a 24/7 autonomous front-desk receptionist named **Sophia** for **Absolute Dental** (Las Vegas, NV):
1. **Zero-Latency Inbound Call Handling**: Instant, human-like voice conversations powered by AssemblyAI Real-Time STT and Cartesia Sonic-2.
2. **Complete Appointment Lifecycle (Book, Reschedule & Cancel)**: 
   - **New Bookings**: Checks live slot availability and books appointments directly via real-time tool calling (`dental_check_appointment_availability` and `dental-clinic-appointment`).
   - **Rescheduling**: Finds patient's existing appointment by name and phone, frees the old calendar slot, and seamlessly moves them to a new requested time.
   - **Cancellations**: Safely cancels bookings and updates clinic records.
3. **Instant WhatsApp Confirmation Notifications**: Automatically dispatches instant WhatsApp booking and rescheduling confirmation messages to patients with date, time, and clinic details via automated n8n workflows.
4. **Live Two-Way Calendar & EHR Sync**: Automatically synchronizes confirmed, rescheduled, and cancelled appointments with Google Calendar and Google Sheets.
5. **Practice Management CRM & Operations Dashboard**: Provides clinic administrators with real-time operational insights, visual monthly booking calendars, AI call transcripts, patient logs, and conversation analytics.

---

## 🏗️ End-to-End System Architecture

```text
       ┌───────────────────────┐
       │   Patient Caller      │
       │ (Web Audio / Browser) │
       └───────────┬───────────┘
                   │ 16kHz PCM Audio Stream (WebSocket)
                   ▼
       ┌──────────────────────────────────────────────────┐
       │         AssemblyAI Streaming Real-Time STT       │
       │    (Universal-3.5, Partial/Final Turn Detection) │
       └───────────────────┬──────────────────────────────┘
                           │ Real-Time User Transcript
                           ▼
       ┌──────────────────────────────────────────────────┐
       │             OpenAI GPT-4o-mini Agent             │
       │     (Clinical Receptionist & Tool Calling)       │
       └───────────┬──────────────────────────┬───────────┘
                   │ Text Response Tokens     │ Tool Calls (Availability / Appointment)
                   ▼                          ▼
       ┌───────────────────────┐  ┌──────────────────────────────────────────────┐
       │   Cartesia Sonic-2    │  │       n8n Webhook Automation Engine          │
       │  Ultra-Low Latency    │  │  - dental_check_appointment_availability     │
       │  Voice Generation     │  │  - dental-clinic-appointment                 │
       │  (Natural Spoken Time)│  │    [Book | Reschedule | Cancel]              │
       └───────────┬───────────┘  └──────┬──────────────────────┬─────────────┬──┘
                   │ Raw PCM Audio Stream│                      │             │
                   ▼                     ▼                      ▼             ▼
       ┌───────────────────────┐  ┌──────────────┐      ┌─────────────┐ ┌───────────────┐
       │ Real-Time Audio Player│  │Google Calendar│     │Google Sheets│ │   WhatsApp    │
       │ (Dynamic Barge-in)    │  │(Live Sync)   │      │(Database)   │ │ Confirmations │
       └───────────────────────┘  └──────┬───────┘      └──────┬──────┘ └───────────────┘
                                         └──────────┬──────────┘
                                                    ▼
                                  ┌───────────────────────────────────┐
                                  │   Dental Clinic Admin CRM         │
                                  │  - Live Operational Calendar      │
                                  │  - Real-Time Practice Metrics     │
                                  │  - AI Call Logs & Transcripts     │
                                  │  - Patient & Appointment Registry │
                                  └───────────────────────────────────┘
```

---

## ⚡ Tech Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Speech-to-Text (STT)** | **AssemblyAI Real-Time Streaming STT** | WebSocket 16kHz streaming transcription with immediate end-of-turn detection |
| **Reasoning Engine (LLM)** | **OpenAI GPT-4o-mini** | Low-latency clinical intent parsing, conversational guardrails, and tool calling |
| **Voice Synthesis (TTS)** | **Cartesia Sonic-2** *(Fallback: ElevenLabs / Deepgram)* | Sub-150ms voice generation with warm, professional healthcare tone and natural spoken time formatting |
| **Tool Automation Engine** | **n8n Production Webhooks (Railway)** | Autonomous calendar checks, multi-system appointment write-backs, and WhatsApp dispatch |
| **Backend & WebSockets** | **FastAPI + Uvicorn + WebSockets** | Asynchronous bi-directional audio pipeline and RESTful CRM API |
| **Database** | **SQLite3 (with thread-safe WAL mode)** | Local, persistent operational store for calls, appointments, and patient profiles |
| **Frontend Interfaces** | **HTML5, CSS3, Modern Vanilla JS** | 1. Patient Voice Portal (`/`)<br>2. Clinical Operations & CRM Dashboard (`/dashboard/`) |
| **Deployment** | **Docker + Railway Cloud** | Containerized unified single-service deployment with automatic HTTPS/WSS |

---

## 🚀 Key Features

### 1. Natural Voice Receptionist ("Sophia")
- **Full Appointment Lifecycle**:
  - **Book New Appointments**: Captures name, phone, date, time, reason for visit, and insurance.
  - **Reschedule Appointments**: Identifies existing bookings by patient name and phone number, frees the old slot, and rebooks at the new requested time.
  - **Cancel Appointments**: Safely removes cancellations from the active clinic roster.
- **Automated WhatsApp Confirmations**: Instantly triggers WhatsApp confirmation and reschedule alert messages to the patient.
- **Dynamic Barge-In Interruption**: Callers can interrupt Sophia at any moment; playback halts instantly within milliseconds and the agent listens.
- **Natural Spoken Time Formatting**: Speeds up and humanizes times (e.g. *"2 PM"*, *"11 AM"*, *"6:56 PM"*) without robotic *"two zero zero"* artifacts.
- **Timezone-Aware Clinical Scheduling**: Evaluates dates and clinic hours grounded in Pacific Time (`America/Los_Angeles`).
- **Multilingual Support**: Speaks English and Spanish, understands Roman Urdu/Hindi.

### 2. Clinical Operations & Admin CRM Dashboard
- **Executive Metric Cards**: Real-time stats on total appointments, conversion rates, call minutes, patient inquiries, and pipeline health.
- **Interactive Monthly Calendar**: Visual grid with clinic working hours, weekend badges, and patient appointment chips.
- **AI Calls Table & Transcript Inspector**: Retell-style badges displaying execution status, payload details, latency, and full conversation transcripts.
- **Appointments & Patients Registry**: Filterable, searchable directory with instant patient record inspection and status management.
- **Role-Based PIN Security**: Protected with biometric/PIN login (`2026`).

---

## 🛠️ Installation & Setup

### 1. Prerequisites
- Python 3.10+
- Modern Web Browser (Chrome / Edge / Safari / Firefox) with microphone permissions enabled

### 2. Clone & Environment Setup
```bash
git clone https://github.com/Mahinn849/dental-care-ai-voice-agent.git
cd dental-care-ai-voice-agent

# Create virtual environment
python -m venv .venv

# Activate environment (Windows)
.venv\Scripts\activate

# Activate environment (Mac/Linux)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure API Keys
Create a `.env` file in the project root:
```env
# AssemblyAI (Required for Streaming STT)
ASSEMBLYAI_API_KEY="your_assemblyai_api_key_here"

# OpenAI (Required for LLM reasoning & function calling)
OPENAI_API_KEY="your_openai_api_key_here"

# Cartesia (Required for ultra-low latency TTS)
CARTESIA_API_KEY="your_cartesia_api_key_here"
CARTESIA_VOICE_ID="db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"

# Fallback TTS
ELEVENLABS_API_KEY="your_elevenlabs_api_key_here"
ELEVENLABS_VOICE_ID="SAz9YHcvj6GT2YYXdXww"

# n8n Webhook Configuration (Deployed on Railway)
N8N_BASE_URL="https://primary-production-930a9.up.railway.app"
N8N_DENTAL_CHECK_AVAILABILITY_WEBHOOK_URL="https://primary-production-930a9.up.railway.app/webhook/dental_check_appointment_availability"
N8N_DENTAL_CLINIC_APPOINTMENT_WEBHOOK_URL="https://primary-production-930a9.up.railway.app/webhook/dental-clinic-appointment"

# CRM Admin Credentials
CRM_ADMIN_USER="admin@absolutedental.com"
CRM_ADMIN_PASS="AbsoluteDental2026!"
CRM_ADMIN_PIN="2026"
```

### 4. Run the Platform Locally
Start the unified FastAPI server:
```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Once running, access:
- **Patient Voice Caller Interface**: [http://localhost:8000/](http://localhost:8000/)
- **Dental Clinic CRM & Admin Dashboard**: [http://localhost:8000/dashboard/](http://localhost:8000/dashboard/) *(PIN: `2026`)*

---

## 🧪 Testing & Validation Suite

Run the automated integration verification suite:
```bash
# 1. Verify Dental Tools Schema, N8N Webhooks & System Prompts
python scratch/test_dental_setup.py

# 2. Verify Live Appointment Actions (Booking, Rescheduling, Cancellation)
python scratch/test_clinicappointment.py

# 3. Verify Natural Speech Text Normalization (Times & Dates)
python scratch/test_clean_text.py

# 4. Verify Cartesia Sonic-2 TTS Latency & Streaming Speed
python scratch/test_cartesia_speed.py
```

---

## ☁️ Deployment (Railway)

CareVoice AI is container-ready with a root `Dockerfile`:
1. Connect this GitHub repository (`dental-care-ai-voice-agent`) to [Railway](https://railway.app).
2. Add your environment variables in the **Variables** tab.
3. Click **"Generate Domain"** under **Settings -> Networking**.
4. Both the **Voice Agent** (`/`) and **CRM Dashboard** (`/dashboard`) will be live on public HTTPS/WSS immediately!

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
