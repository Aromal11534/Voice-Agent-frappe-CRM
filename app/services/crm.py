"""
CRM orchestration service.

Handles the complete post-call workflow:
  1. Extract lead info from transcript
  2. Search for existing lead in Frappe CRM
  3. Create or update the lead
  4. Add AI call summary as a comment
  5. Create follow-up ToDo if required
"""

from __future__ import annotations

import logging

from app.database import get_call_detail, mark_frappe_synced, save_extraction
from app.integrations.frappe import FrappeClient
from app.models.schemas import ExtractedLead, TranscriptEntry
from app.services.extraction import extract_lead_info

logger = logging.getLogger(__name__)


async def process_call_to_crm(
    transcript: list[TranscriptEntry],
    caller_phone: str,
    db_call_id: int | None = None,
    sync_to_frappe: bool = True,
    is_dummy: bool = False,
) -> ExtractedLead | None:
    """
    Full post-call processing pipeline.

    Called after a call ends. Extracts lead data from the transcript
    and saves everything to Frappe CRM.

    Args:
        transcript: The full conversation transcript.
        caller_phone: The caller's phone number.
        db_call_id: PostgreSQL call record ID (for saving extraction results).
        sync_to_frappe: Whether to write the extracted lead to Frappe CRM.

    Returns:
        The extracted lead data, or None if processing failed entirely.
    """
    if not transcript:
        logger.warning("CRM  Empty transcript -- skipping processing")
        return None

    logger.info("=" * 50)
    logger.info("CRM  POST-CALL PROCESSING STARTED")
    logger.info("=" * 50)

    # Step 1: Extract structured data from transcript
    logger.info("CRM  Step 1/4 -- Extracting lead information...")
    extracted = await extract_lead_info(transcript, caller_phone)

    logger.info(f"CRM  Extracted -- Name: {extracted.name}, Intent: {extracted.intent}")
    logger.info(f"CRM  Status: {extracted.lead_status}, Follow-up: {extracted.follow_up_required}")

    # Save extraction to PostgreSQL
    if db_call_id:
        try:
            lead_status_val = extracted.lead_status.value if hasattr(extracted.lead_status, 'value') else str(extracted.lead_status)
            await save_extraction(
                call_id=db_call_id,
                extracted_data=extracted.model_dump(mode="json"),
                lead_status=lead_status_val,
            )
        except Exception:
            logger.warning("CRM  Failed to save extraction to DB")

    # Step 2: Save to Frappe CRM for real calls only. Browser simulations keep
    # their extraction in PostgreSQL without creating fake CRM contacts.
    if sync_to_frappe:
        try:
            await _save_to_frappe(extracted, db_call_id, is_dummy)
        except Exception:
            logger.exception("CRM  Frappe integration failed -- lead data preserved in logs")
            logger.info("CRM  Extracted data remains available in PostgreSQL for retry")
    else:
        logger.info("CRM  Frappe sync skipped for browser simulation")

    logger.info("=" * 50)
    logger.info("CRM  POST-CALL PROCESSING COMPLETE")
    logger.info("=" * 50)

    return extracted


async def _save_to_frappe(extracted: ExtractedLead, db_call_id: int | None = None, is_dummy: bool = False) -> None:
    """
    Save extracted lead data to Frappe CRM.

    Handles the create-or-update logic and follow-up creation.
    """
    frappe = FrappeClient()

    # Step 2: Check for existing lead
    logger.info("CRM  Step 2/4 -- Searching for existing lead...")
    existing_lead = await frappe.find_lead_by_phone(extracted.phone)

    # Build the lead field data
    lead_fields = _build_lead_fields(extracted, is_dummy)

    if existing_lead:
        # Update existing lead
        lead_name = existing_lead["name"]
        logger.info(f"CRM  Lead exists: {lead_name} -- updating...")
        result = await frappe.update_lead(lead_name, lead_fields)
    else:
        # Create new lead
        logger.info("CRM  No existing lead -- creating new...")
        result = await frappe.create_lead(lead_fields)
        lead_name = result.get("name", "") if result else ""

    if not result or not lead_name:
        logger.error("CRM  Failed to create/update lead")
        return

    # Step 3: Add AI summary as a note
    logger.info("CRM  Step 3/4 -- Adding call summary as note...")
    comment_text = _build_comment(extracted)
    await frappe.create_note(comment_text, "CRM Lead", lead_name)

    # Mark as synced in PostgreSQL
    if db_call_id:
        try:
            await mark_frappe_synced(db_call_id, lead_name)
        except Exception:
            logger.warning("CRM  Failed to mark Frappe sync in DB")

    # Step 4: Create follow-up ToDo if required
    if extracted.follow_up_required:
        logger.info("CRM  Step 4/5 -- Creating follow-up ToDo...")
        todo_description = _build_todo_description(extracted, lead_name)
        await frappe.create_todo(
            description=todo_description,
            reference_type="CRM Lead",
            reference_name=lead_name,
        )
        logger.info("CRM  Follow-up ToDo created")
    else:
        logger.info("CRM  Step 4/5 -- No follow-up required, skipping")

    # Step 5: Create CRM Call Log
    if db_call_id:
        call_detail = await get_call_detail(db_call_id)
        if call_detail:
            logger.info("CRM  Step 5/5 -- Creating CRM Call Log...")
            
            def fmt_time(t_str: str | None) -> str | None:
                if not t_str: return None
                return t_str.replace("T", " ")[:19]

            call_log_data = {
                "doctype": "CRM Call Log",
                "id": call_detail.get("call_sid", f"manual-{db_call_id}"),
                "telephony_medium": "Manual",
                "type": "Incoming" if call_detail.get("direction") == "inbound" else "Outgoing",
                "status": "Completed",
                "from": call_detail.get("caller_number", extracted.phone),
                "to": "AI Agent",
                "duration": call_detail.get("duration_sec", 0),
                "start_time": fmt_time(call_detail.get("start_time")),
                "end_time": fmt_time(call_detail.get("end_time")),
                "reference_doctype": "CRM Lead",
                "reference_docname": lead_name,
            }
            if is_dummy:
                call_log_data["from"] = "[TEST] " + call_log_data["from"]
            
            await frappe.create_call_log(call_log_data)

    # Step 6: Create CRM Deal (if Warm/Hot or follow-up required)
    status_str = extracted.lead_status.value if hasattr(extracted.lead_status, 'value') else str(extracted.lead_status)
    if status_str in ("Hot", "Warm") or extracted.follow_up_required:
        logger.info("CRM  Step 6/6 -- Creating CRM Deal...")
        deal_fields = {
            "doctype": "CRM Deal",
            "lead": lead_name,
            "mobile_no": extracted.phone,
        }
        if extracted.budget:
            deal_fields["expected_deal_value"] = extracted.budget
        
        name_parts = (extracted.name or "").strip().split(" ", 1)
        if name_parts and name_parts[0]:
            first_name = name_parts[0]
            if is_dummy:
                first_name = f"[TEST] {first_name}"
            deal_fields["first_name"] = first_name
            if len(name_parts) > 1:
                deal_fields["last_name"] = name_parts[1]
        elif is_dummy:
            deal_fields["first_name"] = "[TEST] Unknown Caller"

        await frappe.create_deal(deal_fields)


def _build_lead_fields(extracted: ExtractedLead, is_dummy: bool = False) -> dict:
    """Build the Frappe CRM Lead field dict from extracted data."""
    fields: dict = {
        "doctype": "CRM Lead",
        "mobile_no": extracted.phone,
    }

    if extracted.name:
        # Split name into first/last if possible
        name_parts = extracted.name.strip().split(" ", 1)
        first_name = name_parts[0]
        if is_dummy:
            first_name = f"[TEST] {first_name}"
        fields["first_name"] = first_name
        if len(name_parts) > 1:
            fields["last_name"] = name_parts[1]
    else:
        fields["first_name"] = "[TEST] Unknown Caller" if is_dummy else "Unknown Caller"

    # Custom fields (created via setup_frappe.py)
    if extracted.language:
        fields["custom_language"] = extracted.language
    if extracted.intent:
        fields["custom_intent"] = extracted.intent
    if extracted.requirement:
        fields["custom_requirement"] = extracted.requirement
    if extracted.budget is not None:
        fields["custom_budget"] = extracted.budget
    if extracted.timeline:
        fields["custom_timeline"] = extracted.timeline
    if extracted.lead_status:
        fields["custom_lead_category"] = extracted.lead_status.value if hasattr(extracted.lead_status, 'value') else extracted.lead_status
    if extracted.summary:
        fields["custom_ai_summary"] = extracted.summary

    return fields


def _build_comment(extracted: ExtractedLead) -> str:
    """Build a formatted comment string for the call summary."""
    lines = [
        "<b>🤖 AI Call Summary</b>",
        "",
        f"<b>Language:</b> {extracted.language}",
    ]

    if extracted.intent:
        lines.append(f"<b>Intent:</b> {extracted.intent}")
    if extracted.requirement:
        lines.append(f"<b>Requirement:</b> {extracted.requirement}")
    if extracted.budget is not None:
        lines.append(f"<b>Budget:</b> ₹{extracted.budget:,.0f}")
    if extracted.timeline:
        lines.append(f"<b>Timeline:</b> {extracted.timeline}")

    lines.append(f"<b>Lead Category:</b> {extracted.lead_status}")
    lines.append("")
    lines.append(f"<b>Summary:</b> {extracted.summary}")

    return "<br>".join(lines)


def _build_todo_description(extracted: ExtractedLead, lead_name: str) -> str:
    """Build a follow-up ToDo description."""
    lines = [
        f"<b>Follow up with {extracted.name or 'caller'}</b>",
        "",
    ]

    if extracted.requirement:
        lines.append(f"Customer requested: {extracted.requirement}")
    if extracted.budget is not None:
        lines.append(f"Budget: ₹{extracted.budget:,.0f}")
    if extracted.timeline:
        lines.append(f"Timeline: {extracted.timeline}")

    lines.append(f"Lead Category: {extracted.lead_status}")
    lines.append(f"Lead: {lead_name}")

    return "<br>".join(lines)
