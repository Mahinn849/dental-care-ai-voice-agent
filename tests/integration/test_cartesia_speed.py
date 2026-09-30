import os
import time
from dotenv import load_dotenv
from cartesia import Cartesia

load_dotenv()
client = Cartesia(api_key=os.getenv("CARTESIA_API_KEY"))

sentences = [
    "I would be happy to help you book an appointment.",
    "What date would you prefer for your visit?",
    "Perfect, your appointment is confirmed for Friday at 2 PM."
]

for s in sentences:
    t0 = time.perf_counter()
    resp = client.tts.generate(
        model_id="sonic-2",
        transcript=s,
        voice={"mode": "id", "id": "79a125e8-cd45-4c13-8a67-188112f4dd22"},
        output_format={"container": "raw", "encoding": "pcm_s16le", "sample_rate": 24000}
    )
    data = resp.read()
    dt = time.perf_counter() - t0
    dur = len(data) / 48000.0
    print(f"Sentence: '{s[:40]}...' -> {len(data)} bytes ({dur:.2f}s) in {dt*1000:.0f}ms (Speed: {dur/dt:.2f}x)", flush=True)
