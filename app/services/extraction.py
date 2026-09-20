"""
LLM-based transcript extraction service.

Takes a call transcript (or raw text) and uses an LLM to extract
structured lead information in JSON format.
"""

from __future__ import annotations

import json
import logging

from app.integrations.sarvam import chat_completion
from app.models.schemas import ExtractedLead, TranscriptEntry
from app.voice.prompts import EXTRACTION_PROMPT

logger = logging.getLogger(__name__)


async def extract_lead_info(
    transcript: list[TranscriptEntry],
    caller_phone: str,
) -> ExtractedLead:
    """
    Extract structured lead data from a conversation transcript.

    Args:
        transcript: List of TranscriptEntry objects from the call session.
        caller_phone: The caller's phone number.

    Returns:
        ExtractedLead with all available fields populated.
    """
    # Format transcript into readable text
    transcript_text = "\n".join(
        f"{'Caller' if entry.role == 'caller' else 'Agent'}: {entry.text}"
        for entry in transcript
    )

    return await extract_lead_info_from_text(transcript_text, caller_phone)


async def extract_lead_info_from_text(
    transcript_text: str,
    caller_phone: str,
) -> ExtractedLead:
    """
    Extract structured lead data from raw transcript text.

    This is the implementation used by both the post-call pipeline
    and the /test/extract development endpoint.

    Args:
        transcript_text: Human-readable transcript text.
        caller_phone: The caller's phone number.

    Returns:
        ExtractedLead with all available fields populated.
    """
    logger.info("EXTRACT  Starting LLM extraction from transcript")
    logger.info(f"EXTRACT  Transcript length: {len(transcript_text)} chars")

    try:
        raw_content = await chat_completion(
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {
                    "role": "user",
                    "content": f"TRANSCRIPT:\n\n{transcript_text}",
                },
            ],
            temperature=0.1,  # Low temperature for consistent extraction
            max_tokens=1000,
            response_format={"type": "json_object"},
        )
        logger.debug("EXTRACT  LLM returned structured data")

        # Parse the JSON response
        extracted = json.loads(raw_content)

        # Build ExtractedLead with phone number always set
        lead = ExtractedLead(
            name=extracted.get("name"),
            phone=caller_phone,
            language=extracted.get("language", "English"),
            intent=extracted.get("intent"),
            requirement=extracted.get("requirement"),
            budget=extracted.get("budget"),
            timeline=extracted.get("timeline"),
            lead_status=extracted.get("lead_status", "Cold"),
            summary=extracted.get("summary", ""),
            follow_up_required=extracted.get("follow_up_required", False),
        )

        logger.info(f"EXTRACT  Result — Intent: {lead.intent}, Status: {lead.lead_status}")
        return lead

    except json.JSONDecodeError:
        logger.exception("EXTRACT  Failed to parse LLM response as JSON")
        return ExtractedLead(phone=caller_phone, summary="Extraction failed — invalid JSON")

    except Exception:
        logger.exception("EXTRACT  LLM extraction failed")
        return ExtractedLead(phone=caller_phone, summary="Extraction failed — LLM error")
