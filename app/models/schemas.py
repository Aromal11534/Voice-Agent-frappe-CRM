"""
Pydantic models (schemas) for the application.

Covers Exotel WebSocket events, extracted lead data,
call sessions, and API request/response shapes.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Enums ───────────────────────────────────────────────────


class LeadCategory(str, Enum):
    """Lead segmentation based on conversation quality."""
    HOT = "Hot"
    WARM = "Warm"
    COLD = "Cold"
    NOT_INTERESTED = "Not Interested"


class ExotelEventType(str, Enum):
    """Event types sent by Exotel over WebSocket."""
    CONNECTED = "connected"
    START = "start"
    MEDIA = "media"
    DTMF = "dtmf"
    MARK = "mark"
    CLEAR = "clear"
    STOP = "stop"


# ── Exotel WebSocket Events ────────────────────────────────


class ExotelStartMetadata(BaseModel):
    """Metadata included in the 'start' event."""
    call_sid: str = Field(alias="callSid", default="")
    stream_sid: str = Field(alias="streamSid", default="")
    account_sid: str = Field(alias="accountSid", default="")
    from_number: str = Field(alias="from", default="")
    to_number: str = Field(alias="to", default="")
    custom_parameters: dict[str, Any] = Field(alias="customParameters", default_factory=dict)

    model_config = {"populate_by_name": True}


class ExotelMediaPayload(BaseModel):
    """Audio payload in the 'media' event."""
    payload: str = ""  # Base64-encoded PCM audio
    timestamp: str = ""
    track: str = ""  # "inbound" or "outbound"
    chunk: str = ""

    model_config = {"populate_by_name": True}


class ExotelEvent(BaseModel):
    """Parsed Exotel WebSocket event."""
    event: ExotelEventType
    sequence_number: str = Field(alias="sequenceNumber", default="")
    stream_sid: str = Field(alias="streamSid", default="")
    start: ExotelStartMetadata | None = None
    media: ExotelMediaPayload | None = None

    model_config = {"populate_by_name": True}


# ── Extracted Lead Data ─────────────────────────────────────


class ExtractedLead(BaseModel):
    """Structured lead information extracted from a call transcript by the LLM."""
    name: str | None = None
    phone: str = ""
    language: str = "English"
    intent: str | None = None
    requirement: str | None = None
    budget: float | None = None
    timeline: str | None = None
    lead_status: LeadCategory = LeadCategory.COLD
    summary: str = ""
    follow_up_required: bool = False


# ── Call Session ────────────────────────────────────────────


class TranscriptEntry(BaseModel):
    """One turn in the conversation."""
    role: Literal["caller", "agent"] = "caller"
    text: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


class CallSession(BaseModel):
    """In-memory state for an active phone call."""
    call_sid: str = ""
    stream_sid: str = ""
    caller_number: str = ""
    start_time: datetime = Field(default_factory=datetime.now)
    transcript: list[TranscriptEntry] = Field(default_factory=list)
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    detected_language: str = "auto"
    is_agent_speaking: bool = False
    call_ended: bool = False


# ── API Request / Response ──────────────────────────────────


class OutboundCallRequest(BaseModel):
    """Request body for POST /calls/outbound."""
    phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")


class OutboundCallResponse(BaseModel):
    """Response for POST /calls/outbound."""
    success: bool
    call_sid: str | None = None
    message: str = ""


class TestExtractRequest(BaseModel):
    """Request body for POST /test/extract."""
    transcript: str = Field(min_length=1, max_length=50_000)
    phone: str = Field(default="+910000000000", pattern=r"^\+[1-9]\d{7,14}$")


class HealthResponse(BaseModel):
    """Response for GET /health."""
    status: str = "ok"
    version: str = "1.0.0"
    services: dict[str, str] = Field(default_factory=dict)
