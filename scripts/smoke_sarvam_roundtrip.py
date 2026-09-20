"""Verify Sarvam TTS -> realtime STT without the application pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.integrations.sarvam import (  # noqa: E402
    connect_stt_stream,
    parse_stt_message,
    send_audio_to_stt,
    text_to_speech_linear16,
)


async def run_roundtrip(
    text: str,
    language_code: str,
    stt_language_code: str,
    mode: str,
) -> dict[str, str]:
    audio = await text_to_speech_linear16(text, language_code)
    if not audio:
        raise RuntimeError("Sarvam TTS returned no audio")

    websocket = await connect_stt_stream(stt_language_code, mode=mode)

    async def receive_final() -> tuple[str, str]:
        async for raw_message in websocket:
            event, transcript, data = parse_stt_message(raw_message)
            if event == "error":
                raise RuntimeError(data.get("message", "Sarvam STT error"))
            if event == "transcript.final" and transcript.strip():
                return transcript, data.get("language") or stt_language_code
        raise RuntimeError("Sarvam STT closed before returning a final transcript")

    receiver = asyncio.create_task(receive_final())
    try:
        chunk_size = 3200
        for offset in range(0, len(audio), chunk_size):
            await send_audio_to_stt(websocket, audio[offset : offset + chunk_size])
            await asyncio.sleep(0.1)
        for _ in range(12):
            await send_audio_to_stt(websocket, b"\x00" * chunk_size)
            await asyncio.sleep(0.1)

        transcript, detected_language = await asyncio.wait_for(receiver, timeout=30)
        return {
            "status": "passed",
            "requested_language": language_code,
            "stt_language": stt_language_code,
            "mode": mode,
            "detected_language": detected_language,
            "transcript": transcript,
        }
    finally:
        if not receiver.done():
            receiver.cancel()
        await websocket.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", default="ml-IN")
    parser.add_argument("--stt-language", default="auto")
    parser.add_argument("--mode", default="transcribe")
    parser.add_argument("--text", default="എനിക്ക് ഒരു വെബ്സൈറ്റ് വേണം")
    args = parser.parse_args()
    result = asyncio.run(
        run_roundtrip(args.text, args.language, args.stt_language, args.mode)
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
