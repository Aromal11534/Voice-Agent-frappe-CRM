"""
Sarvam AI integration for STT, conversational LLM, and TTS.

STT: Uses the Realtime Streaming WebSocket API for low-latency transcription.
TTS: Uses the REST API to convert AI responses to speech audio.
LLM: Uses the Chat Completions API for dialogue and lead extraction.

Audio format notes:
  - Sarvam STT expects 16kHz audio; Exotel sends 8kHz.
  - Sarvam TTS can output mulaw/linear16; we request mulaw at 8kHz for Exotel.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any
from urllib.parse import urlencode

import httpx
import websockets

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────

SARVAM_STT_WS_URL = "wss://api.sarvam.ai/speech-to-text-realtime/ws"
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
SARVAM_CHAT_URL = "https://api.sarvam.ai/v1/chat/completions"


def parse_stt_message(raw_message: str) -> tuple[str, str, dict[str, Any]]:
    """Normalize current and legacy Sarvam realtime STT event shapes."""
    data = json.loads(raw_message)
    event_type = data.get("event") or data.get("type") or ""
    nested = data.get("data") if isinstance(data.get("data"), dict) else {}
    text = (
        data.get("text")
        or data.get("transcript")
        or nested.get("text")
        or nested.get("transcript")
        or ""
    )
    return event_type, text, data


# ── Chat Completions ────────────────────────────────────────


async def chat_completion(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 150,
    response_format: dict[str, Any] | None = None,
) -> str:
    """Generate text with Sarvam's conversational chat model."""
    settings = get_settings()
    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        payload["response_format"] = response_format

    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            SARVAM_CHAT_URL,
            headers={
                "api-subscription-key": settings.sarvam_api_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    choices = data.get("choices") or []
    if not choices:
        raise ValueError("Sarvam chat response contained no choices")
    return (choices[0].get("message", {}).get("content") or "").strip()


# ── Speech-to-Text (Streaming WebSocket) ────────────────────


async def connect_stt_stream(
    language_code: str = "auto",
    mode: str = "codemix",
) -> websockets.WebSocketClientProtocol:
    """
    Establish a WebSocket connection to Sarvam's Realtime STT API.

    Args:
        language_code: BCP-47 code ("ml-IN", "en-IN") or "auto" for auto-detect.

    Returns:
        An open WebSocket connection ready for streaming audio.

    Usage:
        ws = await connect_stt_stream()
        # Send audio chunks:
        await ws.send(json.dumps({"event": "audio_input", "audio": "<base64>"}))
        # Receive transcripts:
        result = await ws.recv()
    """
    settings = get_settings()

    query = urlencode({
        "language_code": language_code,
        "model": settings.sarvam_stt_model,
        # Codemix preserves Malayalam in its native script while keeping
        # English terms readable, which also gives the dialogue model a
        # reliable signal for choosing its response language.
        "mode": mode,
        # Balanced is a better default for bilingual calls: it gives language
        # detection enough context while remaining suitable for voice agents.
        "stream_type": "balanced",
        "endpointing": "vad",
        "encoding": "linear16",
        "sample_rate": 16000,
        "silence_duration_ms": 700,
    })
    uri = f"{SARVAM_STT_WS_URL}?{query}"

    extra_headers = {
        "Api-Subscription-Key": settings.sarvam_api_key,
    }

    logger.info(f"SARVAM STT  Connecting to realtime STT (lang={language_code})")

    ws = await websockets.connect(
        uri,
        additional_headers=extra_headers,
        ping_interval=20,
        ping_timeout=10,
        close_timeout=5,
    )

    logger.info("SARVAM STT  WebSocket connected")
    return ws


async def send_audio_to_stt(
    ws: websockets.WebSocketClientProtocol,
    audio_16k_bytes: bytes,
) -> None:
    """
    Send a chunk of 16kHz PCM audio to the Sarvam STT WebSocket.

    Args:
        ws: The open STT WebSocket connection.
        audio_16k_bytes: Raw PCM audio bytes at 16kHz sample rate.
    """
    audio_b64 = base64.b64encode(audio_16k_bytes).decode("ascii")
    message = json.dumps({"event": "audio_input", "audio": audio_b64})
    await ws.send(message)


# ── Text-to-Speech (REST API) ───────────────────────────────


async def text_to_speech(
    text: str,
    language_code: str = "ml-IN",
) -> bytes:
    """
    Convert text to speech using Sarvam Bulbul TTS.

    Args:
        text: The text to synthesize.
        language_code: BCP-47 code ("ml-IN" for Malayalam, "en-IN" for English).

    Returns:
        Raw audio bytes (PCM mulaw at 8kHz) ready for Exotel playback.
    """
    settings = get_settings()

    payload: dict[str, Any] = {
        "text": text,
        "language_code": language_code,
        "model": settings.sarvam_tts_model,
        "speaker": settings.sarvam_tts_voice,
        # Request mulaw at 8kHz — this is what Exotel expects,
        # so we skip the downsample step entirely.
        "output_audio_codec": "mulaw",
        "speech_sample_rate": 8000,
    }

    logger.info(f"SARVAM TTS  Converting text ({len(text)} chars, lang={language_code})")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                SARVAM_TTS_URL,
                headers={
                    "Api-Subscription-Key": settings.sarvam_api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()

            data = resp.json()
            # Response contains 'audios' array with base64-encoded audio
            audio_b64 = data.get("audios", [None])[0]

            if not audio_b64:
                logger.error("SARVAM TTS  No audio in response")
                return b""

            audio_bytes = base64.b64decode(audio_b64)
            logger.info(f"SARVAM TTS  Generated {len(audio_bytes)} bytes of audio")
            return audio_bytes

    except Exception:
        logger.exception("SARVAM TTS  Failed to generate speech")
        return b""


async def text_to_speech_linear16(
    text: str,
    language_code: str = "ml-IN",
) -> bytes:
    """
    Convert text to speech as linear16 PCM at 16kHz.

    This variant is useful if we need to do additional processing
    before sending to Exotel (where we'd then downsample).

    Returns:
        Raw 16kHz linear16 PCM bytes.
    """
    settings = get_settings()

    payload: dict[str, Any] = {
        "text": text,
        "language_code": language_code,
        "model": settings.sarvam_tts_model,
        "speaker": settings.sarvam_tts_voice,
        "output_audio_codec": "linear16",
        "speech_sample_rate": 16000,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                SARVAM_TTS_URL,
                headers={
                    "Api-Subscription-Key": settings.sarvam_api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()

            data = resp.json()
            audio_b64 = data.get("audios", [None])[0]

            if not audio_b64:
                return b""

            return base64.b64decode(audio_b64)

    except Exception:
        logger.exception("SARVAM TTS  Failed to generate linear16 speech")
        return b""
