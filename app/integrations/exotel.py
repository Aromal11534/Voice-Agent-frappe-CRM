"""
Exotel telephony integration.

Handles:
  - Parsing Exotel WebSocket events (media, start, stop, etc.)
  - Building audio response messages for Exotel
  - Initiating outbound calls via Exotel REST API
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.models.schemas import (
    ExotelEvent,
    ExotelEventType,
    ExotelMediaPayload,
    ExotelStartMetadata,
)

logger = logging.getLogger(__name__)


# ── Event Parsing ───────────────────────────────────────────


def parse_exotel_event(raw_message: str) -> ExotelEvent:
    """
    Parse a raw JSON message from Exotel WebSocket into a typed event.

    Args:
        raw_message: Raw JSON string from the WebSocket.

    Returns:
        Parsed ExotelEvent with appropriate sub-fields populated.
    """
    data = json.loads(raw_message)

    event_type = data.get("event", "")

    event = ExotelEvent(
        event=event_type,
        sequenceNumber=data.get("sequenceNumber", ""),
        streamSid=data.get("streamSid", ""),
    )

    if event_type == ExotelEventType.START and "start" in data:
        event.start = ExotelStartMetadata(**data["start"])

    elif event_type == ExotelEventType.MEDIA and "media" in data:
        event.media = ExotelMediaPayload(**data["media"])

    return event


# ── Response Building ───────────────────────────────────────


def build_media_message(audio_b64: str, stream_sid: str) -> str:
    """
    Build a JSON message to send audio back to the caller via Exotel.

    Args:
        audio_b64: Base64-encoded audio payload.
        stream_sid: The stream SID from the current session.

    Returns:
        JSON string ready to send over the WebSocket.
    """
    return json.dumps({
        "event": "media",
        "streamSid": stream_sid,
        "media": {
            "payload": audio_b64,
        },
    })


def build_mark_message(stream_sid: str, mark_name: str = "end_of_speech") -> str:
    """
    Build a mark event to track when audio playback completes.

    Args:
        stream_sid: The stream SID from the current session.
        mark_name: Identifier for this mark event.

    Returns:
        JSON string ready to send over the WebSocket.
    """
    return json.dumps({
        "event": "mark",
        "streamSid": stream_sid,
        "mark": {
            "name": mark_name,
        },
    })


def build_clear_message(stream_sid: str) -> str:
    """
    Build a clear event to stop/interrupt audio playback on Exotel side.

    Args:
        stream_sid: The stream SID from the current session.

    Returns:
        JSON string ready to send over the WebSocket.
    """
    return json.dumps({
        "event": "clear",
        "streamSid": stream_sid,
    })


# ── Outbound Call API ───────────────────────────────────────


async def initiate_outbound_call(to_number: str) -> dict[str, Any]:
    """
    Initiate an outbound call via Exotel Connect API.

    The called party will hear the AI agent. The call audio is routed
    to our WebSocket endpoint via the StreamUrl parameter.

    Args:
        to_number: Phone number to call (E.164 format).

    Returns:
        Dict with call details including call_sid.

    Raises:
        Exception: If the API call fails.
    """
    settings = get_settings()

    url = f"{settings.exotel_base_url}/v1/Accounts/{settings.exotel_sid}/Calls/connect"

    # The WebSocket URL that Exotel will connect to
    ws_url = settings.server_url.replace("https://", "wss://").replace("http://", "ws://")
    stream_url = f"{ws_url}/voice?direction=outbound"

    payload = {
        "From": to_number,
        "CallerId": settings.exotel_phone,
        "StreamUrl": stream_url,
        "StreamType": "bidirectional",
    }

    logger.info("EXOTEL  Initiating outbound call")
    logger.info(f"EXOTEL  StreamUrl: {stream_url}")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            url,
            data=payload,  # Exotel expects form-encoded data
            auth=(settings.exotel_api_key, settings.exotel_api_token),
        )
        resp.raise_for_status()

        result = resp.json()
        call_sid = result.get("Call", {}).get("Sid", "")

        logger.info(f"EXOTEL  Outbound call initiated — Call SID: {call_sid}")

        return {"call_sid": call_sid, "raw": result}
