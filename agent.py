import os
import asyncio
import json
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
import pyaudio
import requests
import websockets
from dotenv import load_dotenv
from openai import AsyncOpenAI
from elevenlabs.client import ElevenLabs

from backend.utils.text_speech import clean_text_for_speech

load_dotenv()
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
DEEPGRAM_TTS_MODEL = os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-helena-en")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

if not ASSEMBLYAI_API_KEY:
    raise ValueError("ASSEMBLYAI_API_KEY .env file mein nahi mili.")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY .env file mein nahi mili.")
if not DEEPGRAM_API_KEY and not ELEVENLABS_API_KEY:
    raise ValueError("DEEPGRAM_API_KEY ya ELEVENLABS_API_KEY .env file mein nahi mili.")

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
OPENAI_MODEL = "gpt-4.1-mini"

elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY) if ELEVENLABS_API_KEY else None
TTS_MODEL = "eleven_flash_v2_5"
TTS_VOICE = os.getenv("ELEVENLABS_VOICE_ID", "SAz9YHcvj6GT2YYXdXww")
TTS_SPEED = 1.05

ASSEMBLYAI_WS = "wss://streaming.assemblyai.com/v3/ws"
SAMPLE_RATE = 16000
CHANNELS = 1
FRAMES_PER_BUFFER = 800
AUDIO_FORMAT = pyaudio.paInt16

def get_las_vegas_datetime():
    las_vegas_time = datetime.now(ZoneInfo("America/Los_Angeles"))
    return las_vegas_time.strftime("%A, %B %d, %Y at %I:%M %p")

def build_system_prompt():
    current_datetime = get_las_vegas_datetime()
    return f"""## Role

You are **Sophia**, an AI front desk receptionist for Absolute dental clinic in Las Vegas, Nevada. Your job is to greet callers, help patients book, reschedule, or cancel appointments, answer general clinic questions, and transfer to a human when requested.

## Working Hours
- Current time: {current_datetime} (America/Los_Angeles timezone).
- Office hours: Monday to Friday, 8:00 AM to 5:00 PM Pacific. Closed Saturday and Sunday.
- Appointments may only be scheduled Monday through Friday, between 8:00 AM and 4:00 PM.

## Multilingual Handling
You speak **English** and **Spanish**. Always begin the call in English. If the patient speaks Spanish or requests it, switch immediately and continue entirely in Spanish.

## Clinic Information
- Location: 8380 W Cheyenne Ave Ste 102, Las Vegas, NV 89129
- Hours: Monday to Friday 8:00 AM - 5:00 PM; Saturday and Sunday closed

CONVERSATION STYLE:
Be concise, friendly, natural and conversational. Keep most answers to one or two short sentences.
"""

conversation_history = []
speaking_event = threading.Event()
processing_event = threading.Event()
stop_event = threading.Event()

# NEW: Signals ElevenLabs playback to stop when the caller interrupts.
tts_stop_event = threading.Event()
active_response_task = None
response_lock = asyncio.Lock()

audio = None
mic_stream = None
speaker_stream = None

last_processed_transcript = ""
last_processed_time = 0
DUPLICATE_WINDOW = 2.0

GREETING_TEXT = (
    "Thank you for calling Absolute Dental in Las Vegas. "
    "My name is Sophia. How can I help you today?"
)

def setup_microphone():
    global audio
    global mic_stream
    audio = pyaudio.PyAudio()
    mic_stream = audio.open(
        format=AUDIO_FORMAT,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=FRAMES_PER_BUFFER
    )
    print("🎤 Microphone ready.")

def setup_speaker():
    global speaker_stream
    if audio is None:
        raise RuntimeError("PyAudio is not initialized.")
    speaker_stream = audio.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=24000,
        output=True,
        frames_per_buffer=2048
    )
    print("🔊 Speaker stream ready")

async def send_audio(websocket):
    print("🎤 Microphone streaming started...")
    try:
        while not stop_event.is_set():
            audio_data = await asyncio.to_thread(
                mic_stream.read,
                FRAMES_PER_BUFFER,
                False
            )
            # NEW: Keep sending mic audio while Sophia speaks.
            # Without this, AssemblyAI cannot detect interruptions.
            await websocket.send(audio_data)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"\n❌ Microphone error: {e}")

async def ask_gpt_stream(user_text, sentence_queue):
    """Stream GPT text and queue natural chunks for TTS.
    We intentionally do NOT send every token to TTS. Chunks are released
    at punctuation or after a reasonable character count, preventing the
    word-by-word stop/start effect.
    """
    global conversation_history
    conversation_history.append({"role": "user", "content": user_text})
    recent_history = conversation_history[-12:]
    messages = [{"role": "system", "content": build_system_prompt()}]
    messages.extend(recent_history)
    start_time = time.perf_counter()
    first_token_time = None
    full_response = ""
    buffer = ""
    MIN_CHUNK_CHARS = 45
    MAX_CHUNK_CHARS = 120
    print("\n🤖 Sophia: ", end="", flush=True)
    try:
        stream = await openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=120,
            stream=True,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if not delta:
                continue
            if first_token_time is None:
                first_token_time = time.perf_counter() - start_time
                print(f"\n⚡ First GPT token: {first_token_time:.2f}s")
                print("🤖 Sophia: ", end="", flush=True)
            full_response += delta
            buffer += delta
            print(delta, end="", flush=True)

            # NEW: Stop adding new speech after an interruption.
            if tts_stop_event.is_set():
                continue

            while True:
                sentence, remaining = extract_complete_sentence(buffer)
                if sentence:
                    await sentence_queue.put(sentence)
                    buffer = remaining
                    continue
                if len(buffer) >= MAX_CHUNK_CHARS:
                    cut = buffer.rfind(" ", 0, MAX_CHUNK_CHARS)
                    if cut >= MIN_CHUNK_CHARS:
                        await sentence_queue.put(buffer[:cut].strip())
                        buffer = buffer[cut:].lstrip()
                break

        if buffer.strip() and not tts_stop_event.is_set():
            await sentence_queue.put(buffer.strip())

        await sentence_queue.put(None)
        full_response = full_response.strip()
        conversation_history.append({"role": "assistant", "content": full_response})
        print()
        print(f"⏱️ GPT total: {time.perf_counter() - start_time:.2f}s")
        return full_response
    except Exception as e:
        print(f"\n❌ GPT error: {e}")
        await sentence_queue.put(None)
        return ""

def extract_complete_sentence(buffer):
    punctuation_marks = [".", "?", "!", ":"]
    earliest_position = None
    for mark in punctuation_marks:
        position = buffer.find(mark)
        if position != -1:
            if earliest_position is None or position < earliest_position:
                earliest_position = position
    if earliest_position is None:
        return None, buffer
    sentence = buffer[:earliest_position + 1].strip()
    remaining = buffer[earliest_position + 1:]
    return sentence, remaining

def speak_streaming_sync(text):
    if not text.strip():
        return
    global speaker_stream
    start_time = time.perf_counter()
    first_audio_time = None

    speaking_event.set()

    cleaned_text = clean_text_for_speech(text)

    # Primary TTS: Deepgram Aura-2
    if DEEPGRAM_API_KEY:
        print(f"\n🔊 Deepgram Aura-2 TTS starting: {cleaned_text}")
        try:
            url = "https://api.deepgram.com/v1/speak"
            headers = {
                "Authorization": f"Token {DEEPGRAM_API_KEY}",
                "Content-Type": "application/json"
            }
            params = {
                "model": DEEPGRAM_TTS_MODEL,
                "encoding": "linear16",
                "sample_rate": 24000,
                "container": "none"
            }
            with requests.post(url, headers=headers, params=params, json={"text": cleaned_text}, stream=True) as resp:
                if resp.status_code != 200:
                    print(f"\n❌ Deepgram TTS error: HTTP {resp.status_code} - {resp.text}")
                    return
                for chunk in resp.iter_content(chunk_size=2048):
                    if tts_stop_event.is_set():
                        print("\n🛑 TTS interrupted by caller.")
                        break
                    if not chunk:
                        continue
                    if first_audio_time is None:
                        first_audio_time = time.perf_counter() - start_time
                        print(f"⚡ First TTS audio: {first_audio_time:.2f}s")
                    speaker_stream.write(
                        chunk,
                        exception_on_underflow=False
                    )
            total_time = time.perf_counter() - start_time
            print(f"⏱️ Deepgram Aura-2 TTS total: {total_time:.2f}s")
            return
        except Exception as e:
            print(f"\n❌ Deepgram TTS error: {e}")
        finally:
            speaking_event.clear()

    # Fallback to ElevenLabs if Deepgram not configured
    if elevenlabs_client:
        print(f"\n🔊 ElevenLabs TTS fallback starting: {cleaned_text}")
        try:
            audio_stream = elevenlabs_client.text_to_speech.stream(
                voice_id=TTS_VOICE,
                output_format="pcm_24000",
                text=cleaned_text,
                model_id=TTS_MODEL
            )
            for audio_chunk in audio_stream:
                if tts_stop_event.is_set():
                    print("\n🛑 TTS interrupted by caller.")
                    break
                if not audio_chunk:
                    continue
                if first_audio_time is None:
                    first_audio_time = time.perf_counter() - start_time
                    print(f"⚡ First TTS audio: {first_audio_time:.2f}s")
                speaker_stream.write(
                    audio_chunk,
                    exception_on_underflow=False
                )
            total_time = time.perf_counter() - start_time
            print(f"⏱️ ElevenLabs TTS total: {total_time:.2f}s")
        except Exception as e:
            print(f"\n❌ ElevenLabs TTS error: {e}")
        finally:
            speaking_event.clear()

def play_startup_greeting():
    print("\n👋 Sophia is starting...")
    print(f"🔊 Greeting: {GREETING_TEXT}")
    speak_streaming_sync(GREETING_TEXT)
    print("\n✅ Sophia finished the welcome greeting.")
    print("🎤 Sophia is now ready for your voice.")

async def process_tts_queue(sentence_queue):
    """Play natural TTS chunks one after another without word-by-word gaps."""
    tts_start = time.perf_counter()
    first_chunk = True
    while True:
        sentence = await sentence_queue.get()
        if sentence is None:
            break
        if not sentence.strip():
            continue

        if tts_stop_event.is_set():
            print("⏭️ Discarding queued TTS after interruption.")
            continue

        if first_chunk:
            print(f"\n🔊 TTS starting: {sentence}")
            first_chunk = False
        else:
            print(f"\n🔊 Next TTS chunk: {sentence}")

        await asyncio.to_thread(speak_streaming_sync, sentence)

        if tts_stop_event.is_set():
            print("🛑 TTS queue stopped because caller interrupted.")
            break

    print(f"\n⏱️ TTS queue total: {time.perf_counter() - tts_start:.2f}s")

async def process_user_message(user_text):
    global active_response_task
    if not user_text.strip():
        return

    processing_event.set()
    total_start = time.perf_counter()
    sentence_queue = asyncio.Queue()
    print(f"\n🗣️ You: {user_text}")
    try:
        tts_task = asyncio.create_task(process_tts_queue(sentence_queue))
        await ask_gpt_stream(user_text, sentence_queue)
        await tts_task
        print("\n--------------------------------------------")
        print(f"📊 Response total: {time.perf_counter() - total_start:.2f}s")
        print("--------------------------------------------")
    except asyncio.CancelledError:
        print("\n🛑 Current GPT response cancelled due to interruption.")
        raise
    except Exception as e:
        print(f"\n❌ GPT/TTS pipeline error: {e}")
    finally:
        processing_event.clear()
        if active_response_task is asyncio.current_task():
            active_response_task = None

async def receive_transcripts(websocket):
    global last_processed_transcript
    global active_response_task
    global last_processed_time
    print("👂 Listening for AssemblyAI transcripts...")
    try:
        async for raw_message in websocket:
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                continue
            event_type = message.get("type")

            if event_type == "Begin":
                session_id = message.get("id")
                print(f"\n✅ AssemblyAI session started: {session_id}")
                print("\n👋 Sophia is starting her welcome...")
                await asyncio.to_thread(play_startup_greeting)
                print("\n🎙️ Sophia is ready. Speak now...")

            elif event_type == "Turn":
                transcript = message.get("transcript", "").strip()
                end_of_turn = message.get("end_of_turn", False)
                if not transcript:
                    continue

                if not end_of_turn:
                    print(f"\r📝 You: {transcript}", end="", flush=True)

                    # NEW: Partial transcripts are used for barge-in detection.
                    # AssemblyAI is now still receiving mic audio while Sophia speaks.
                    if speaking_event.is_set() and len(transcript) >= 3:
                        if not tts_stop_event.is_set():
                            print("\n🛑 Caller interruption detected!")
                        tts_stop_event.set()
                        if active_response_task and not active_response_task.done():
                            active_response_task.cancel()

                else:
                    print("\r" + (" " * 120) + "\r", end="")
                    print(f"📝 Final: {transcript}")

                    current_time = time.perf_counter()
                    same_transcript = transcript.lower() == last_processed_transcript.lower()
                    too_soon = current_time - last_processed_time < DUPLICATE_WINDOW

                    if same_transcript and too_soon:
                        print("⏭️ Duplicate transcript ignored.")
                        continue

                    last_processed_transcript = transcript
                    last_processed_time = current_time

                    # After an interruption, accept the caller's complete sentence
                    # and start a fresh response instead of ignoring it.
                    if active_response_task and not active_response_task.done():
                        print("⏭️ A response is already active; waiting for the new turn.")
                        continue

                    tts_stop_event.clear()
                    active_response_task = asyncio.create_task(process_user_message(transcript))

            elif event_type == "Termination":
                print("\n🛑 AssemblyAI session terminated.")
                break

            elif event_type == "Error":
                print(f"\n❌ AssemblyAI error: {message}")

    except websockets.exceptions.ConnectionClosed:
        print("\n🔌 AssemblyAI connection closed.")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"\n❌ Transcript receive error: {e}")

async def main():
    global audio
    global mic_stream
    global speaker_stream

    print("=" * 60)
    print("        CAREVOICE AI - SOPHIA")
    print("=" * 60)
    print(f"🤖 LLM: {OPENAI_MODEL}")
    print("🎙️ STT: AssemblyAI Universal-3.5 Pro Realtime")
    tts_display = f"Deepgram Aura-2 ({DEEPGRAM_TTS_MODEL})" if DEEPGRAM_API_KEY else f"ElevenLabs ({TTS_MODEL})"
    print(f"📝 TTS: {tts_display}")
    print(f"📅 Las Vegas Time: {get_las_vegas_datetime()}")
    print("=" * 60)

    setup_microphone()
    setup_speaker()

    params = {
        "sample_rate": SAMPLE_RATE,
        "speech_model": "universal-3-5-pro"
    }
    url = f"{ASSEMBLYAI_WS}?{urlencode(params)}"

    print("\n🔌 Connecting to AssemblyAI...")
    try:
        async with websockets.connect(
            url,
            additional_headers={"Authorization": ASSEMBLYAI_API_KEY}
        ) as websocket:
            print("✅ Connected to AssemblyAI!")
            print("🚀 Voice agent is now running.")
            print("💡 Press Ctrl+C to stop.")

            send_task = asyncio.create_task(send_audio(websocket))
            receive_task = asyncio.create_task(receive_transcripts(websocket))

            try:
                await asyncio.gather(send_task, receive_task)
            except asyncio.CancelledError:
                pass
            except KeyboardInterrupt:
                print("\n👋 Stopping Sophia...")
            finally:
                stop_event.set()
                tts_stop_event.set()
                send_task.cancel()
                receive_task.cancel()
                try:
                    await websocket.send(json.dumps({"type": "Terminate"}))
                except Exception:
                    pass
    except KeyboardInterrupt:
        print("\n👋 Sophia stopped.")
    except Exception as e:
        print(f"\n❌ Connection error: {e}")
    finally:
        try:
            if mic_stream:
                mic_stream.stop_stream()
                mic_stream.close()
        except Exception:
            pass
        try:
            if speaker_stream:
                speaker_stream.stop_stream()
                speaker_stream.close()
        except Exception:
            pass
        try:
            if audio:
                audio.terminate()
        except Exception:
            pass
        print("\n✅ Resources cleaned up.")

if __name__ == "__main__":
    asyncio.run(main())
