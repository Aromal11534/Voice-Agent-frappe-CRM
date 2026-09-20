"""
Browser-based Voice Pipeline.

Handles raw 16kHz PCM audio streaming directly from a web browser,
bypassing the Exotel telephony requirement. Useful for testing and demos.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect

from app.config import get_settings, is_configured
from app.database import save_call_start, save_call_end, save_transcript_entry
from app.integrations.sarvam import (
    chat_completion,
    connect_stt_stream,
    parse_stt_message,
    send_audio_to_stt,
    text_to_speech_linear16,
)
from app.models.schemas import CallSession, TranscriptEntry
from app.services.crm import process_call_to_crm
from app.voice.prompts import (
    FALLBACK_RESPONSE,
    FALLBACK_RESPONSE_ML,
    GREETING,
    MALAYALAM_TURN_INSTRUCTION,
    SALES_AGENT_PROMPT,
)

logger = logging.getLogger(__name__)


async def handle_browser_call(websocket: WebSocket) -> None:
    """
    Handle a direct browser WebRTC/WebSocket audio stream.
    Receives 16kHz PCM binary data, sends back 16kHz PCM binary data.
    """
    if not is_configured(get_settings().sarvam_api_key):
        await websocket.send_text(json.dumps({
            "event": "error",
            "message": "SARVAM_API_KEY is not configured on the server.",
        }))
        await websocket.close(code=1011, reason="Sarvam is not configured")
        return

    caller_phone = websocket.query_params.get("phone")
    caller_name = websocket.query_params.get("name")

    session = CallSession()
    session.call_sid = f"browser_{uuid4().hex}"
    session.caller_number = caller_phone.strip() if caller_phone and caller_phone.strip() else "browser-simulator"
    session.start_time = datetime.now()

    stt_ws = None
    stt_listener_task = None
    db_call_id: int | None = None
    transcript_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

    logger.info("=" * 50)
    logger.info("BROWSER CALL STARTED")
    logger.info(f"  Session ID : {session.call_sid}")
    logger.info("=" * 50)

    try:
        # Save to PostgreSQL
        try:
            db_call_id = await save_call_start(
                call_sid=session.call_sid,
                caller_number=session.caller_number,
                direction="inbound",
            )
        except Exception:
            logger.warning("BROWSER PIPELINE  Failed to save call start to DB")

        # Connect STT
        logger.info("BROWSER PIPELINE  Connecting to Sarvam STT...")
        try:
            stt_ws = await connect_stt_stream(language_code="auto")
        except Exception:
            logger.exception("BROWSER PIPELINE  Failed to connect to Sarvam STT")
            await websocket.close()
            return

        stt_listener_task = asyncio.create_task(_stt_listener(stt_ws, transcript_queue))

        # Send greeting
        logger.info("BROWSER PIPELINE  Sending greeting...")
        session.conversation_history.append({"role": "system", "content": SALES_AGENT_PROMPT})
        
        if caller_name and caller_name.strip():
            system_note = f"The caller's name is {caller_name.strip()}."
            session.conversation_history.append({"role": "system", "content": system_note})
            session.transcript.append(TranscriptEntry(role="caller", text=f"My name is {caller_name.strip()}."))
            if db_call_id:
                try:
                    await save_transcript_entry(db_call_id, "caller", f"My name is {caller_name.strip()}.")
                except Exception:
                    pass

        session.conversation_history.append({"role": "assistant", "content": GREETING})
        session.transcript.append(TranscriptEntry(role="agent", text=GREETING))
        
        if db_call_id:
            try:
                await save_transcript_entry(db_call_id, "agent", GREETING)
            except Exception:
                pass

        await _send_tts_response(websocket, session, GREETING, "en-IN")

        # Main Loop
        logger.info("BROWSER PIPELINE  Entering conversation loop...")
        browser_task = asyncio.create_task(_browser_audio_receiver(websocket, session, stt_ws))

        while not session.call_ended:
            try:
                transcript_text, detected_language = await asyncio.wait_for(
                    transcript_queue.get(), timeout=1.0
                )
                if not transcript_text.strip():
                    continue

                if any("\u0D00" <= ch <= "\u0D7F" for ch in transcript_text):
                    session.detected_language = "ml-IN"
                elif detected_language in {"en-IN", "ml-IN"}:
                    session.detected_language = detected_language

                logger.debug("CALLER  Transcript received (%s chars)", len(transcript_text))

                session.transcript.append(TranscriptEntry(role="caller", text=transcript_text))
                session.conversation_history.append({"role": "user", "content": transcript_text})

                if db_call_id:
                    try:
                        await save_transcript_entry(db_call_id, "caller", transcript_text)
                    except Exception:
                        pass

                # Get LLM Response
                ai_response = await _get_llm_response(session)

                if ai_response:
                    session.transcript.append(TranscriptEntry(role="agent", text=ai_response))
                    session.conversation_history.append({"role": "assistant", "content": ai_response})

                    if db_call_id:
                        try:
                            await save_transcript_entry(db_call_id, "agent", ai_response)
                        except Exception:
                            pass

                    lang_code = _detect_tts_language(
                        transcript_text,
                        ai_response,
                        session.detected_language,
                    )
                    await _send_tts_response(websocket, session, ai_response, lang_code)

            except asyncio.TimeoutError:
                if browser_task.done():
                    break
                continue
            except Exception:
                logger.exception("BROWSER PIPELINE  Error in conversation loop")
                continue

        if not browser_task.done():
            browser_task.cancel()
            try:
                await browser_task
            except asyncio.CancelledError:
                pass

    except WebSocketDisconnect:
        logger.info("BROWSER PIPELINE  Browser disconnected")
    except Exception:
        logger.exception("BROWSER PIPELINE  Fatal error in pipeline")
    finally:
        session.call_ended = True
        if stt_ws:
            try:
                await stt_ws.close()
            except Exception:
                pass
        if stt_listener_task and not stt_listener_task.done():
            stt_listener_task.cancel()
            try:
                await stt_listener_task
            except asyncio.CancelledError:
                pass

        duration = (datetime.now() - session.start_time).seconds
        if db_call_id:
            try:
                await save_call_end(db_call_id, duration)
            except Exception:
                pass

        logger.info("=" * 50)
        logger.info("BROWSER CALL ENDED")
        logger.info(f"  Duration  : {duration}s")
        logger.info("=" * 50)

        if session.transcript:
            logger.info("BROWSER PIPELINE  Starting local lead extraction...")
            try:
                await process_call_to_crm(
                    session.transcript,
                    session.caller_number,
                    db_call_id,
                    sync_to_frappe=True,
                    is_dummy=True,
                )
            except Exception:
                logger.exception("BROWSER PIPELINE  Lead extraction failed")


async def _browser_audio_receiver(websocket: WebSocket, session: CallSession, stt_ws) -> None:
    try:
        while not session.call_ended:
            message = await websocket.receive()
            if "bytes" in message:
                audio_16k = message["bytes"]
                if stt_ws and not session.is_agent_speaking:
                    try:
                        await send_audio_to_stt(stt_ws, audio_16k)
                    except Exception:
                        logger.warning("BROWSER PIPELINE  Failed to send audio to STT")
            elif "text" in message:
                try:
                    data = json.loads(message["text"])
                    if data.get("event") == "clear":
                        logger.info("BROWSER PIPELINE  Barge-in detected")
                        session.is_agent_speaking = False
                    elif data.get("event") == "stop":
                        session.call_ended = True
                        break
                except Exception:
                    pass
    except Exception:
        session.call_ended = True


async def _stt_listener(
    stt_ws,
    transcript_queue: asyncio.Queue[tuple[str, str]],
) -> None:
    try:
        async for raw_message in stt_ws:
            try:
                event_type, text, data = parse_stt_message(raw_message)
                if event_type == "transcript.final":
                    if text.strip():
                        language = data.get("language") or ""
                        logger.info(
                            "BROWSER STT FINAL  %s (language=%s)",
                            text,
                            language or "unspecified",
                        )
                        await transcript_queue.put((text, language))
                elif event_type == "transcript.partial":
                    if text.strip():
                        logger.debug("BROWSER STT PARTIAL  %s", text)
                elif event_type == "error":
                    logger.error(
                        "BROWSER STT ERROR  %s",
                        data.get("message", "unknown error"),
                    )
            except json.JSONDecodeError:
                logger.warning("BROWSER STT  Received a non-JSON message")
    except Exception:
        logger.exception("BROWSER STT  Listener ended unexpectedly")


async def _get_llm_response(session: CallSession) -> str:
    try:
        messages = list(session.conversation_history)
        if session.detected_language == "ml-IN":
            messages.insert(
                1,
                {"role": "system", "content": MALAYALAM_TURN_INSTRUCTION},
            )
        return await chat_completion(messages, temperature=0.7, max_tokens=150)
    except Exception:
        logger.exception("SARVAM LLM  Failed to get browser-call response")
        if session.detected_language == "ml-IN":
            return FALLBACK_RESPONSE_ML
        return FALLBACK_RESPONSE


async def _send_tts_response(websocket: WebSocket, session: CallSession, text: str, language_code: str) -> None:
    if not text:
        return
    # We use linear16 at 16kHz because it's easiest to play in browser via AudioContext
    audio_bytes = await text_to_speech_linear16(text, language_code)
    if not audio_bytes:
        return

    chunk_size = 3200  # 100ms chunks at 16kHz 16-bit
    session.is_agent_speaking = True
    
    try:
        await websocket.send_text(json.dumps({"event": "playback_start"}))
    except Exception:
        pass

    for i in range(0, len(audio_bytes), chunk_size):
        if session.call_ended or not session.is_agent_speaking:
            break
        chunk = audio_bytes[i: i + chunk_size]
        try:
            await websocket.send_bytes(chunk)
            await asyncio.sleep(0.09) # Pace the audio slightly faster than real-time to avoid buffer underrun
        except Exception:
            break

    session.is_agent_speaking = False
    try:
        await websocket.send_text(json.dumps({"event": "playback_complete"}))
    except Exception:
        pass


def _detect_tts_language(
    caller_text: str,
    ai_response: str,
    detected_language: str = "auto",
) -> str:
    has_malayalam = any("\u0D00" <= ch <= "\u0D7F" for ch in ai_response + caller_text)
    return "ml-IN" if has_malayalam or detected_language == "ml-IN" else "en-IN"
