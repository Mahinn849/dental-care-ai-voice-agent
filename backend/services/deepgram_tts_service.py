"""
CareVoice AI - Deepgram Aura-2 Realtime Streaming TTS Service
Provides a high-performance, low-latency WebSocket client for Deepgram Aura-2 Text-to-Speech (TTS).

Architecture:
- Persistent WebSocket connection (wss://api.deepgram.com/v1/speak)
- Linear16 24kHz raw PCM streaming without container headers (container=none)
- Control messages:
    - 'Speak': streams text chunks as LLM tokens arrive
    - 'Flush': forces immediate synthesis at the end of assistant turns
    - 'Clear': instant interruption / barge-in cancellation of buffered audio
    - 'Close': graceful shutdown
- HTTP REST fallback for resilience
"""

import asyncio
import json
import os
import time
from typing import AsyncGenerator, Optional
import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from backend.utils.text_speech import clean_text_for_speech

DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/speak"
DEEPGRAM_REST_URL = "https://api.deepgram.com/v1/speak"


class DeepgramTTSWebSocketSession:
    """Manages an active real-time streaming TTS session over WebSocket with Deepgram Aura-2."""

    def __init__(self, api_key: str, model: str = "aura-2-helena-en", sample_rate: int = 24000):
        self.api_key = api_key
        self.model = model
        self.sample_rate = sample_rate
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        self.audio_queue: asyncio.Queue = asyncio.Queue()
        self._reader_task: Optional[asyncio.Task] = None
        self._is_flushed = asyncio.Event()
        self._lock = asyncio.Lock()

    @property
    def url(self) -> str:
        return f"{DEEPGRAM_WS_URL}?model={self.model}&encoding=linear16&sample_rate={self.sample_rate}&container=none"

    @property
    def _is_open(self) -> bool:
        """Checks if the underlying WebSocket is open and operational."""
        if not self.is_connected or not self.ws:
            return False
        if hasattr(self.ws, "state"):
            from websockets.protocol import State
            return self.ws.state == State.OPEN
        if hasattr(self.ws, "closed"):
            return not self.ws.closed
        return self.is_connected

    async def connect(self) -> bool:
        """Establishes WebSocket connection to Deepgram TTS."""
        async with self._lock:
            if self._is_open:
                return True
            try:
                headers = {"Authorization": f"Token {self.api_key}"}
                self.ws = await websockets.connect(
                    self.url,
                    additional_headers=headers,
                    ping_interval=20,
                    ping_timeout=20,
                )
                # First message is connection metadata
                meta_raw = await self.ws.recv()
                self.is_connected = True
                self._is_flushed.set()
                self._reader_task = asyncio.create_task(self._read_loop())
                print(f"[Deepgram TTS WS] Connected successfully to Aura-2 ({self.model})")
                return True
            except Exception as e:
                print(f"[Deepgram TTS WS] Connection failed: {e}")
                self.is_connected = False
                return False

    async def _read_loop(self):
        """Continuously reads incoming binary audio frames and control messages from Deepgram."""
        try:
            while self._is_open:
                msg = await self.ws.recv()
                if isinstance(msg, bytes):
                    await self.audio_queue.put(msg)
                elif isinstance(msg, str):
                    try:
                        data = json.loads(msg)
                        msg_type = data.get("type")
                        if msg_type == "Flushed":
                            self._is_flushed.set()
                        elif msg_type == "Cleared":
                            # Deepgram confirmed audio queue flushed on server
                            self._clear_local_queue()
                    except json.JSONDecodeError:
                        pass
        except ConnectionClosed:
            print("[Deepgram TTS WS] Connection closed by server.")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[Deepgram TTS WS] Reader loop error: {e}")
        finally:
            self.is_connected = False
            self._is_flushed.set()

    def _clear_local_queue(self):
        """Empties pending audio chunks in local memory queue."""
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def speak(self, text: str):
        """Streams a text fragment to Deepgram for synthesis."""
        if not text.strip():
            return
        if not self._is_open:
            connected = await self.connect()
            if not connected:
                return

        self._is_flushed.clear()
        try:
            await self.ws.send(json.dumps({"type": "Speak", "text": text}))
        except Exception as e:
            print(f"[Deepgram TTS WS] Failed to send Speak message: {e}")
            self.is_connected = False

    async def flush(self, wait_timeout: float = 4.0):
        """Signals Deepgram to process all remaining text and wait for completion."""
        if not self._is_open:
            return
        try:
            await self.ws.send(json.dumps({"type": "Flush"}))
            try:
                await asyncio.wait_for(self._is_flushed.wait(), timeout=wait_timeout)
            except asyncio.TimeoutError:
                pass
        except Exception as e:
            print(f"[Deepgram TTS WS] Failed to send Flush: {e}")
            self.is_connected = False

    async def clear(self):
        """Immediately cancels and purges in-flight synthesis for interruption (barge-in)."""
        self._clear_local_queue()
        self._is_flushed.set()
        if self._is_open:
            try:
                await self.ws.send(json.dumps({"type": "Clear"}))
            except Exception as e:
                print(f"[Deepgram TTS WS] Failed to send Clear: {e}")

    async def close(self):
        """Gracefully closes the WebSocket connection."""
        self.is_connected = False
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        if self.ws:
            try:
                if self._is_open:
                    await self.ws.send(json.dumps({"type": "Close"}))
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
        self._clear_local_queue()
