"""End-to-end smoke test for the browser voice-agent pipeline.

The script synthesizes a caller utterance with Sarvam, streams it through the
same WebSocket used by the dashboard, and requires a second audio playback from
the agent.  It intentionally exercises TTS -> STT -> LLM -> TTS rather than
mocking any provider.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import websockets

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.integrations.sarvam import text_to_speech_linear16  # noqa: E402


async def _receive_playback(websocket, label: str, timeout_seconds: float) -> int:
    """Wait for one complete server playback and return its audio byte count."""
    started = False
    audio_bytes = 0

    while True:
        message = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
        if isinstance(message, bytes):
            if started:
                audio_bytes += len(message)
            continue

        payload = json.loads(message)
        event = payload.get("event")
        if event == "error":
            raise RuntimeError(payload.get("message", "Voice pipeline returned an error"))
        if event == "playback_start":
            started = True
        elif event == "playback_complete" and started:
            if audio_bytes == 0:
                raise RuntimeError(f"{label} playback completed without audio")
            return audio_bytes


async def run_smoke_test(
    uri: str,
    utterance: str,
    language_code: str,
) -> dict[str, int | str]:
    caller_audio = await text_to_speech_linear16(utterance, language_code)
    if not caller_audio:
        raise RuntimeError("Sarvam did not generate caller test audio")

    async with websockets.connect(uri, max_size=None, open_timeout=15) as websocket:
        greeting_bytes = await _receive_playback(websocket, "Greeting", 45)

        # The server and Sarvam both expect 16 kHz, mono, signed 16-bit PCM.
        # Pace chunks in real time so endpointing behaves like a microphone.
        chunk_size = 3200
        for offset in range(0, len(caller_audio), chunk_size):
            await websocket.send(caller_audio[offset : offset + chunk_size])
            await asyncio.sleep(0.1)

        # Give VAD an unambiguous end-of-utterance signal.
        silence_chunk = b"\x00" * chunk_size
        for _ in range(12):
            await websocket.send(silence_chunk)
            await asyncio.sleep(0.1)

        response_bytes = await _receive_playback(websocket, "Agent response", 60)
        await websocket.send(json.dumps({"event": "stop"}))

    return {
        "status": "passed",
        "caller_audio_bytes": len(caller_audio),
        "greeting_audio_bytes": greeting_bytes,
        "response_audio_bytes": response_bytes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--uri",
        default="ws://localhost:8000/voice/browser",
        help="Browser voice WebSocket URL",
    )
    parser.add_argument(
        "--utterance",
        default="Hello, I need a website for my business.",
        help="Caller phrase to synthesize and stream",
    )
    parser.add_argument(
        "--language",
        default="en-IN",
        choices=("en-IN", "ml-IN"),
        help="Language used to synthesize the caller phrase",
    )
    args = parser.parse_args()

    result = asyncio.run(run_smoke_test(args.uri, args.utterance, args.language))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
