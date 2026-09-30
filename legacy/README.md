# Legacy Voice Agent Implementations

This directory contains early prototypes and experimental scripts retained strictly for architectural reference and provenance.

### Files:
- **`agent_terminal_pyaudio.py`**:
  - **Purpose**: An early desktop/CLI terminal prototype that utilized local hardware microphone streaming via PyAudio.
  - **Status**: **Legacy / Deprecated for Web**. PyAudio relies on platform-specific C libraries (`portaudio`) and physical hardware soundcards, which are unavailable in containerized cloud environments (e.g., Docker, Railway).
  
### Production Voice Agent:
- The active, production-grade voice agent is located in **`backend/services/browser_voice_service.py`**.
- It provides a full-duplex WebSocket audio interface (`/api/ws/voice`), natively streaming raw 16kHz PCM from browser microphones to **AssemblyAI Streaming STT**, reasoning with **OpenAI GPT-4o-mini**, synthesizing ultra-low latency voice with **Cartesia Sonic-2**, and executing live appointments through **n8n**.
