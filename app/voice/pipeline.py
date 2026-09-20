"""
Voice pipeline — the core of the AI voice agent.

Manages the full-duplex WebSocket conversation with Exotel:
  1. Receives audio from Exotel (caller's speech)
  2. Forwards to Sarvam STT for real-time transcription
  3. Sends transcript to LLM for response generation
  4. Converts LLM response to speech via Sarvam TTS
  5. Streams TTS audio back to Exotel (caller hears response)
  6. On call end, triggers post-call CRM processing

This file handles the real-time audio pipeline, conversation state,
and the coordination between all three external services.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime

from fastapi import WebSocket
from app.config import get_settings
from app.database import save_call_start, save_call_end, save_transcript_entry
from app.integrations.exotel import (
    build_mark_message,
    build_media_message,
    parse_exotel_event,
)
from app.integrations.sarvam import (
    chat_completion,
    connect_stt_stream,
    parse_stt_message,
    send_audio_to_stt,
    text_to_speech,
)
from app.models.schemas import (
    CallSession,
    ExotelEventType,
    TranscriptEntry,
)
from app.services.crm import process_call_to_crm
from app.voice.audio import StreamingResampler, chunk_audio
from app.voice.prompts import (
    FALLBACK_RESPONSE,
    FALLBACK_RESPONSE_ML,
    GREETING,
    MALAYALAM_TURN_INSTRUCTION,
    SALES_AGENT_PROMPT,
)

logger = logging.getLogger(__name__)


# ── Main Call Handler ───────────────────────────────────────


async def handle_call(websocket: WebSocket, direction: str = "inbound") -> None:
    """
    Main entry point for handling a live phone call.

    Called from the /voice WebSocket endpoint. Manages the entire
    call lifecycle from connection to post-call processing.
    """
    session = CallSession()
    stt_ws = None
    stt_listener_task = None
    db_call_id: int | None = None  # PostgreSQL call record ID
    received_start = False

    # Queue for passing transcripts from STT listener to the main loop
    transcript_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

    try:
        # ── Phase 1: Wait for Exotel 'start' event ──────────

        logger.info("PIPELINE  Waiting for Exotel start event...")

        # Process messages until we get a 'start' event
        async for raw_message in websocket.iter_text():
            event = parse_exotel_event(raw_message)

            if event.event == ExotelEventType.CONNECTED:
                logger.info("PIPELINE  Exotel connected")
                continue

            if event.event == ExotelEventType.START:
                if event.start:
                    session.call_sid = event.start.call_sid
                    session.stream_sid = event.start.stream_sid
                    session.caller_number = event.start.from_number
                    session.start_time = datetime.now()

                logger.info("=" * 50)
                logger.info("CALL STARTED")
                logger.info(f"  Call SID : {session.call_sid}")
                logger.info(f"  Caller   : {session.caller_number}")
                logger.info(f"  Stream   : {session.stream_sid}")
                logger.info("=" * 50)

                # Save to PostgreSQL
                try:
                    db_call_id = await save_call_start(
                        call_sid=session.call_sid,
                        caller_number=session.caller_number,
                        direction="outbound" if direction == "outbound" else "inbound",
                    )
                except Exception:
                    logger.warning("PIPELINE  Failed to save call start to DB")

                received_start = True
                break

        if not received_start:
            logger.warning("PIPELINE  Connection ended before Exotel start event")
            return

        # ── Phase 2: Initialize STT stream ──────────────────

        logger.info("PIPELINE  Connecting to Sarvam STT...")
        try:
            stt_ws = await connect_stt_stream(language_code="auto")
        except Exception:
            logger.exception("PIPELINE  Failed to connect to Sarvam STT")
            # Send a fallback audio message and close
            await _send_tts_response(websocket, session, FALLBACK_RESPONSE, "en-IN")
            return

        # Start background task to listen for STT transcripts
        stt_listener_task = asyncio.create_task(
            _stt_listener(stt_ws, transcript_queue)
        )

        # ── Phase 3: Send greeting ──────────────────────────

        logger.info("PIPELINE  Sending greeting...")
        session.conversation_history.append(
            {"role": "system", "content": SALES_AGENT_PROMPT}
        )
        session.conversation_history.append(
            {"role": "assistant", "content": GREETING}
        )
        session.transcript.append(
            TranscriptEntry(role="agent", text=GREETING)
        )
        if db_call_id:
            try:
                await save_transcript_entry(db_call_id, "agent", GREETING)
            except Exception:
                logger.warning("PIPELINE  Failed to persist greeting")

        await _send_tts_response(websocket, session, GREETING, "en-IN")

        # ── Phase 4: Main conversation loop ─────────────────

        logger.info("PIPELINE  Entering conversation loop...")

        # We need to listen for both Exotel events and STT transcripts
        # concurrently. Use a task for Exotel and check transcript_queue.

        exotel_task = asyncio.create_task(
            _exotel_audio_receiver(websocket, session, stt_ws)
        )

        # Process transcripts as they arrive
        while not session.call_ended:
            try:
                # Wait for a transcript with timeout
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

                # Add to transcript
                session.transcript.append(
                    TranscriptEntry(role="caller", text=transcript_text)
                )
                session.conversation_history.append(
                    {"role": "user", "content": transcript_text}
                )

                # Save caller turn to PostgreSQL
                if db_call_id:
                    try:
                        await save_transcript_entry(db_call_id, "caller", transcript_text)
                    except Exception:
                        pass

                # Generate AI response
                ai_response = await _get_llm_response(session)

                if ai_response:
                    logger.debug("AI  Response generated (%s chars)", len(ai_response))

                    session.transcript.append(
                        TranscriptEntry(role="agent", text=ai_response)
                    )
                    session.conversation_history.append(
                        {"role": "assistant", "content": ai_response}
                    )

                    # Save agent turn to PostgreSQL
                    if db_call_id:
                        try:
                            await save_transcript_entry(db_call_id, "agent", ai_response)
                        except Exception:
                            pass

                    # Detect language for TTS
                    lang_code = _detect_tts_language(
                        transcript_text,
                        ai_response,
                        session.detected_language,
                    )

                    # Convert to speech and send back
                    await _send_tts_response(websocket, session, ai_response, lang_code)

            except asyncio.TimeoutError:
                # No transcript received — check if call still active
                if exotel_task.done():
                    break
                continue

            except Exception:
                logger.exception("PIPELINE  Error in conversation loop")
                continue

        # Cancel the Exotel receiver task
        if not exotel_task.done():
            exotel_task.cancel()
            try:
                await exotel_task
            except asyncio.CancelledError:
                pass

    except Exception:
        logger.exception("PIPELINE  Fatal error in voice pipeline")

    finally:
        # ── Phase 5: Cleanup & Post-call processing ─────────

        session.call_ended = True

        # Close STT WebSocket
        if stt_ws:
            try:
                await stt_ws.close()
            except Exception:
                pass

        # Cancel STT listener
        if stt_listener_task and not stt_listener_task.done():
            stt_listener_task.cancel()
            try:
                await stt_listener_task
            except asyncio.CancelledError:
                pass

        logger.info("=" * 50)
        logger.info("CALL ENDED")
        logger.info(f"  Call SID  : {session.call_sid}")
        logger.info(f"  Duration  : {(datetime.now() - session.start_time).seconds}s")
        logger.info(f"  Turns     : {len(session.transcript)}")
        logger.info("=" * 50)

        # Save call end to PostgreSQL
        duration = (datetime.now() - session.start_time).seconds
        if db_call_id:
            try:
                await save_call_end(db_call_id, duration)
            except Exception:
                logger.warning("PIPELINE  Failed to save call end to DB")

        logger.info("PIPELINE  Transcript captured with %s turns", len(session.transcript))

        # Finish post-call processing before releasing the handler so work isn't lost.
        if session.transcript and session.caller_number:
            logger.info("PIPELINE  Starting post-call CRM processing...")
            try:
                await process_call_to_crm(
                    session.transcript, session.caller_number, db_call_id
                )
            except Exception:
                logger.exception("PIPELINE  Post-call CRM processing failed")
        else:
            logger.warning("PIPELINE  No transcript or caller number -- skipping CRM")


# ── Exotel Audio Receiver ──────────────────────────────────


async def _exotel_audio_receiver(
    websocket: WebSocket,
    session: CallSession,
    stt_ws,
) -> None:
    """
    Background task that receives audio from Exotel and forwards to STT.

    Runs continuously until the call ends (stop event or disconnect).
    """
    try:
        resampler = StreamingResampler()
        async for raw_message in websocket.iter_text():
            if session.call_ended:
                break

            event = parse_exotel_event(raw_message)

            if event.event == ExotelEventType.MEDIA and event.media:
                # Decode audio from Exotel (8kHz PCM base64)
                audio_8k = base64.b64decode(event.media.payload)

                # Upsample to 16kHz for Sarvam STT
                audio_16k = resampler.process(audio_8k)

                # Forward to STT stream
                if stt_ws:
                    try:
                        await send_audio_to_stt(stt_ws, audio_16k)
                    except Exception:
                        logger.warning("PIPELINE  Failed to send audio to STT")

            elif event.event == ExotelEventType.CLEAR:
                # Caller interrupted — stop current TTS playback
                logger.info("PIPELINE  Barge-in detected — clearing playback")
                session.is_agent_speaking = False

            elif event.event == ExotelEventType.STOP:
                logger.info("PIPELINE  Exotel stop event received")
                session.call_ended = True
                break

            elif event.event == ExotelEventType.DTMF:
                logger.info("PIPELINE  DTMF received (ignored)")

    except Exception:
        logger.info("PIPELINE  Exotel audio receiver ended")
        session.call_ended = True


# ── STT Transcript Listener ────────────────────────────────


async def _stt_listener(
    stt_ws,
    transcript_queue: asyncio.Queue[tuple[str, str]],
) -> None:
    """
    Background task that listens for transcripts from Sarvam STT WebSocket.

    Parses different event types:
      - transcript.partial: interim results (ignored for LLM, logged)
      - transcript.final: complete utterance (sent to LLM)
    """
    try:
        async for raw_message in stt_ws:
            try:
                event_type, text, data = parse_stt_message(raw_message)

                if event_type == "transcript.partial":
                    # Interim result — log but don't process
                    if text:
                        logger.debug(f"STT PARTIAL  {text}")

                elif event_type == "transcript.final":
                    # Final result — send to conversation loop
                    if text and text.strip():
                        language = data.get("language") or ""
                        logger.info(
                            "STT FINAL  %s (language=%s)",
                            text,
                            language or "unspecified",
                        )
                        await transcript_queue.put((text, language))

                elif event_type == "transcript":
                    # Legacy format — treat as final
                    if text and text.strip():
                        logger.info(f"STT  {text}")
                        await transcript_queue.put((text, ""))

                elif event_type == "error":
                    error_msg = data.get("message", "unknown error")
                    logger.error(f"STT ERROR  {error_msg}")

                else:
                    # Log unknown event types for debugging
                    logger.debug(f"STT EVENT  {event_type}: {data}")

            except json.JSONDecodeError:
                logger.warning(f"STT  Non-JSON message: {raw_message[:100]}")

    except Exception:
        logger.info("STT  Listener ended")


# ── LLM Response Generation ────────────────────────────────


async def _get_llm_response(session: CallSession) -> str:
    """
    Get AI response from the LLM based on conversation history.

    Args:
        session: Current call session with conversation history.

    Returns:
        The AI's text response, or fallback message on failure.
    """
    try:
        messages = list(session.conversation_history)
        if session.detected_language == "ml-IN":
            messages.insert(
                1,
                {"role": "system", "content": MALAYALAM_TURN_INSTRUCTION},
            )
        return await chat_completion(
            messages,
            temperature=0.7,
            max_tokens=150,  # Keep responses short for voice
        )

    except Exception:
        logger.exception("SARVAM LLM  Failed to get response")
        if session.detected_language == "ml-IN":
            return FALLBACK_RESPONSE_ML
        return FALLBACK_RESPONSE


# ── TTS & Audio Streaming ──────────────────────────────────


async def _send_tts_response(
    websocket: WebSocket,
    session: CallSession,
    text: str,
    language_code: str = "en-IN",
) -> None:
    """
    Convert text to speech and stream audio back to the caller via Exotel.

    Steps:
      1. Call Sarvam TTS to get audio bytes
      2. Chunk the audio into Exotel-compatible sizes
      3. Send each chunk as a media event over the WebSocket
      4. Send a mark event to track playback completion
    """
    if not text:
        return

    # Generate speech audio
    audio_bytes = await text_to_speech(text, language_code)

    if not audio_bytes:
        logger.warning("TTS  No audio generated — skipping")
        return

    # For 8-bit mulaw at 8kHz, 320 bytes represents 40ms of audio.
    chunks = chunk_audio(audio_bytes, chunk_size=320, padding_byte=b"\xff")

    logger.info(f"TTS  Streaming {len(chunks)} audio chunks to caller")

    session.is_agent_speaking = True
    for i, chunk in enumerate(chunks):
        if session.call_ended or not session.is_agent_speaking:
            break

        audio_b64 = base64.b64encode(chunk).decode("ascii")
        message = build_media_message(audio_b64, session.stream_sid)

        try:
            await websocket.send_text(message)
        except Exception:
            logger.warning(f"TTS  Failed to send chunk {i}/{len(chunks)}")
            break

        await asyncio.sleep(0.04)

    session.is_agent_speaking = False

    # Send mark to track when playback completes
    try:
        mark_msg = build_mark_message(session.stream_sid, f"tts_{len(session.transcript)}")
        await websocket.send_text(mark_msg)
    except Exception:
        pass


# ── Language Detection ──────────────────────────────────────


def _detect_tts_language(
    caller_text: str,
    ai_response: str,
    detected_language: str = "auto",
) -> str:
    """
    Detect the appropriate TTS language code based on conversation content.

    Simple heuristic: if the AI response contains Malayalam characters,
    use ml-IN. Otherwise, use en-IN.
    """
    # Check for Malayalam Unicode range (U+0D00 to U+0D7F)
    has_malayalam = any("\u0D00" <= ch <= "\u0D7F" for ch in ai_response)

    if has_malayalam:
        return "ml-IN"

    # Also check caller's text for language context
    caller_has_malayalam = any("\u0D00" <= ch <= "\u0D7F" for ch in caller_text)

    if caller_has_malayalam or detected_language == "ml-IN":
        return "ml-IN"

    return "en-IN"
