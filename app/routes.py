"""
API route definitions.

All FastAPI endpoints are defined here and mounted on the main app.
The WebSocket /voice endpoint is the core — it handles live Exotel calls.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status

from app.config import get_settings, is_configured
from app.database import check_db
from app.models.schemas import (
    HealthResponse,
    OutboundCallRequest,
    OutboundCallResponse,
    TestExtractRequest,
    ExtractedLead,
)
from app.integrations.exotel import initiate_outbound_call
from app.services.extraction import extract_lead_info_from_text
from app.security import require_api_token
from app.voice.pipeline import handle_call

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Health & Info ───────────────────────────────────────────


@router.get("/", tags=["info"])
async def root():
    """Welcome endpoint with basic project info."""
    return {
        "project": "AI Voice Agent + Frappe CRM",
        "version": "1.0.0",
        "description": "AI-powered voice agent that handles calls and saves leads to Frappe CRM",
        "endpoints": {
            "health": "/health",
            "voice_ws": "/voice",
            "outbound": "/calls/outbound",
            "test_extract": "/test/extract",
        },
    }


@router.get("/health", response_model=HealthResponse, tags=["info"])
async def health_check():
    """
    Health check that verifies connectivity to external services.
    Returns status of each service integration.
    """
    settings = get_settings()
    services = {"database": "connected" if await check_db() else "unavailable"}

    # Check Sarvam API key presence
    services["sarvam"] = "configured" if is_configured(settings.sarvam_api_key) else "missing_key"

    # Check Frappe URL presence
    services["frappe"] = "configured" if is_configured(
        settings.frappe_url,
        settings.frappe_api_key,
        settings.frappe_api_secret,
    ) else "missing_credentials"

    # Check Exotel credentials
    services["exotel"] = "configured" if is_configured(
        settings.exotel_sid,
        settings.exotel_api_key,
        settings.exotel_api_token,
        settings.exotel_phone,
    ) else "missing_credentials"

    # Sarvam chat completions use the same subscription key as STT and TTS.
    services["llm"] = "configured" if is_configured(settings.sarvam_api_key) else "missing_key"

    healthy_values = {"configured", "connected"}
    overall = "ok" if all(v in healthy_values for v in services.values()) else "degraded"

    return HealthResponse(status=overall, services=services)


# ── Voice WebSocket ─────────────────────────────────────────


@router.websocket("/voice")
async def voice_endpoint(websocket: WebSocket):
    """
    Exotel WebSocket endpoint for bidirectional voice streaming.

    Exotel connects here when a call is routed through the Voicebot Applet.
    This handler manages the entire call lifecycle:
      1. Accept connection
      2. Receive audio → STT → LLM → TTS → send audio back
      3. On call end → extract lead info → save to Frappe CRM
    """
    await websocket.accept()
    logger.info("VOICE WS  WebSocket connection accepted")

    try:
        direction = websocket.query_params.get("direction", "inbound")
        await handle_call(websocket, direction=direction)
    except WebSocketDisconnect:
        logger.info("VOICE WS  WebSocket disconnected (caller hung up)")
    except Exception:
        logger.exception("VOICE WS  Unexpected error in voice pipeline")


@router.websocket("/voice/browser")
async def browser_voice_endpoint(websocket: WebSocket):
    """
    Direct browser WebSocket endpoint for testing the AI agent via laptop microphone.
    Receives raw 16kHz PCM audio instead of Exotel telephony payloads.
    """
    from app.voice.browser_pipeline import handle_browser_call

    await websocket.accept()
    logger.info("BROWSER WS  WebSocket connection accepted")

    try:
        await handle_browser_call(websocket)
    except WebSocketDisconnect:
        logger.info("BROWSER WS  WebSocket disconnected")
    except Exception:
        logger.exception("BROWSER WS  Unexpected error in browser pipeline")


# ── Outbound Calling ────────────────────────────────────────


@router.post(
    "/calls/outbound",
    response_model=OutboundCallResponse,
    tags=["calls"],
)
async def outbound_call(
    request: OutboundCallRequest,
    _: None = Depends(require_api_token),
):
    """
    Trigger an outbound call via Exotel.

    The called party hears the AI agent. The conversation is processed
    the same way as an incoming call.
    """
    logger.info("OUTBOUND  Initiating requested call")

    try:
        result = await initiate_outbound_call(request.phone)
        return OutboundCallResponse(
            success=True,
            call_sid=result.get("call_sid"),
            message="Outbound call initiated successfully",
        )
    except Exception:
        logger.exception("OUTBOUND  Failed to initiate call")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to initiate outbound call",
        )


# ── Test / Development ──────────────────────────────────────


@router.post(
    "/test/extract",
    response_model=ExtractedLead,
    tags=["dev"],
)
async def test_extraction(
    request: TestExtractRequest,
    _: None = Depends(require_api_token),
):
    """
    Development endpoint: submit a raw transcript and get structured lead extraction.
    Useful for testing without making actual phone calls.
    """
    logger.info("TEST  Running extraction on provided transcript")

    result = await extract_lead_info_from_text(request.transcript, request.phone)
    return result
