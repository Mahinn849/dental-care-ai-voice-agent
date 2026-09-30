# CareVoice AI 🎙️🦷
### Autonomous Dental Clinic Voice Receptionist & Real-Time Operational CRM

> **CareVoice AI** is an intelligent, ultra-low latency healthcare voice AI receptionist and clinical management system built for dental practices. Powered by **AssemblyAI Streaming WebSocket STT**, **Cartesia Sonic-2 Voice Synthesis**, **OpenAI GPT-4o-mini**, and an end-to-end automated **n8n Webhook & Google Calendar/Sheets Integration**, accompanied by a full-fledged **Dental Practice CRM & Admin Dashboard**.

---

## 🌟 Executive Summary & Problem Solved

Dental clinics and specialty practices lose over **30% of incoming patient bookings** due to missed calls after hours, staff overload during peak clinical procedures, and friction in scheduling. 

**CareVoice AI** acts as a 24/7 autonomous front-desk receptionist named **Sophia** for **SmileCraft Dental**:
1. **Zero-Latency Inbound Call Handling**: Instant, human-like voice conversations powered by AssemblyAI Real-Time STT and Cartesia Sonic-2.
2. **Autonomous Clinical Scheduling**: Checks live slot availability and books appointments directly via real-time tool calling (`dental_check_appointment_availability` and `dental-clinic-appointment`).
3. **Live Two-Way Calendar & EHR Sync**: Automatically synchronizes confirmed appointments with Google Calendar and Google Sheets via n8n automation pipelines.
4. **Practice Management CRM & Operations Dashboard**: Provides clinic administrators with real-time operational insights, visual monthly booking calendars, AI call transcripts, patient logs, and conversation analytics.

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
       │    (Universal-2, Partial/Final Turn Detection)   │
       └───────────────────┬──────────────────────────────┘
                           │ User Transcript
                           ▼
       ┌──────────────────────────────────────────────────┐
       │             OpenAI GPT-4o-mini Agent             │
       │        (Clinical Persona & Function Calling)     │
       └───────────┬──────────────────────────┬───────────┘
                   │ Text Response Tokens     │ Tool Calls
                   ▼                          ▼
       ┌───────────────────────┐  ┌───────────────────────────────────┐
       │   Cartesia Sonic-2    │  │  n8n Webhook Automation Engine    │
       │  Ultra-Low Latency    │  │   - dental_check_availability     │
       │  Voice Generation     │  │   - dental_book_appointment      │
       └───────────┬───────────┘  └─────────────────┬─────────────────┘
                   │ Raw PCM Audio Stream           │ 
                   ▼                                ▼
       ┌───────────────────────┐  ┌───────────────────────────────────┐
       │ Real-Time Audio Player│  │  Google Calendar & Google Sheets  │
       │ (Dynamic Barge-in)    │  └─────────────────┬─────────────────┘
       └───────────────────────┘                    │
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
| **Voice Synthesis (TTS)** | **Cartesia Sonic-2** *(Fallback: ElevenLabs / Deepgram / OpenAI)* | Sub-150ms voice generation with warm, professional healthcare tone |
| **Tool Automation Engine** | **n8n Webhook Service** | Autonomous calendar availability checks and multi-system appointment write-backs |
| **Backend & WebSockets** | **FastAPI + Uvicorn + WebSockets** | Asynchronous bi-directional audio pipeline and RESTful CRM API |
| **Database** | **SQLite3 (with thread-safe WAL mode)** | Local, persistent operational store for calls, appointments, and patient profiles |
| **Frontend Interfaces** | **HTML5, CSS3, Modern Vanilla JS** | 1. Patient Voice Portal (`/`)<br>2. Clinical Operations & CRM Dashboard (`/dashboard/`) |

---

## 🚀 Key Features

### 1. Natural Voice Receptionist ("Sophia")
- **Dynamic Barge-In Interruption**: Callers can interrupt Sophia at any moment; playback halts instantly within milliseconds and the agent listens.
- **Timezone-Aware Clinical Scheduling**: Evaluates relative dates (*"tomorrow afternoon"*, *"next Monday at 10 AM"*) grounded in the clinic's local timezone.
- **Medical Triage Safety**: Strictly avoids dispensing unauthorized medical diagnoses; prioritizes urgent dental symptoms (severe swelling, trauma) for immediate emergency slots.

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
- Modern Web Browser (Chrome / Edge / Firefox) with microphone permissions enabled

### 2. Clone & Environment Setup
```bash
git clone https://github.com/your-username/carevoice-ai.git
cd carevoice-ai

# Create virtual environment
python -m venv .venv

# Activate environment (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt
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

# Optional Fallbacks
ELEVENLABS_API_KEY=""
DEEPGRAM_API_KEY=""

# n8n Webhook Configuration
N8N_WEBHOOK_URL="https://your-n8n-instance.com/webhook/dental-clinic-appointment"
```

### 4. Run the Platform
Start the unified FastAPI server:
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Once running, access:
- **Patient Voice Caller Interface**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Dental Clinic CRM & Admin Dashboard**: [http://127.0.0.1:8000/dashboard/](http://127.0.0.1:8000/dashboard/) *(PIN: `2026`)*

---

## 🧪 Testing & Validation

Run the automated integration verification suite:
```bash
# Verify AssemblyAI STT & tool calling
python backend/tests/test_booking_tool_call.py
python backend/tests/test_availability_tool_call.py

# Verify CRM SQLite sync
python scratch/test_crm_api.py
```

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

