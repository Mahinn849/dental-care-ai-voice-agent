"""
CareVoice AI - Voice API Routes
WebSocket endpoints for browser-based voice streaming.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.services.browser_voice_service import BrowserVoiceSession

router = APIRouter(tags=["voice"])


@router.websocket("/api/ws/voice")
@router.websocket("/ws/voice")
async def voice_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time bidirectional browser voice communication.
    Receives raw 16kHz PCM audio and sends clean transcript and TTS events.
    Supports both /api/ws/voice and /ws/voice.
    """
    await websocket.accept()
    session = BrowserVoiceSession(websocket)
    try:
        await session.run()
    except WebSocketDisconnect:
        print("[Voice WS] Client disconnected from /api/ws/voice")
    except Exception as e:
        print(f"[Voice WS Error] {e}")
