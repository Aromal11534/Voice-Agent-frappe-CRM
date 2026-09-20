"""
One-time Frappe CRM setup script.

Creates custom fields on the CRM Lead DocType to store AI-extracted data.
Run this once before using the voice agent:

    python -m scripts.setup_frappe

Prerequisites:
  - Frappe CRM instance running and accessible
  - API credentials configured in .env
  - User has System Manager or Administrator role
"""

from __future__ import annotations

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from app.config import get_settings


# ── Custom Fields Definition ────────────────────────────────

CUSTOM_FIELDS = [
    {
        "dt": "CRM Lead",
        "fieldname": "custom_language",
        "label": "Language",
        "fieldtype": "Data",
        "insert_after": "mobile_no",
        "description": "Detected language of the caller",
    },
    {
        "dt": "CRM Lead",
        "fieldname": "custom_intent",
        "label": "Intent / Service",
        "fieldtype": "Data",
        "insert_after": "custom_language",
        "description": "Service or product the caller is interested in",
    },
    {
        "dt": "CRM Lead",
        "fieldname": "custom_requirement",
        "label": "Requirement",
        "fieldtype": "Small Text",
        "insert_after": "custom_intent",
        "description": "Detailed requirement from the caller",
    },
    {
        "dt": "CRM Lead",
        "fieldname": "custom_budget",
        "label": "Budget (₹)",
        "fieldtype": "Currency",
        "insert_after": "custom_requirement",
        "description": "Approximate budget mentioned by the caller",
    },
    {
        "dt": "CRM Lead",
        "fieldname": "custom_timeline",
        "label": "Timeline",
        "fieldtype": "Data",
        "insert_after": "custom_budget",
        "description": "Expected timeline mentioned by the caller",
    },
    {
        "dt": "CRM Lead",
        "fieldname": "custom_lead_category",
        "label": "Lead Category",
        "fieldtype": "Select",
        "options": "\nHot\nWarm\nCold\nNot Interested",
        "insert_after": "custom_timeline",
        "description": "AI-classified lead category",
    },
    {
        "dt": "CRM Lead",
        "fieldname": "custom_ai_summary",
        "label": "AI Summary",
        "fieldtype": "Small Text",
        "insert_after": "custom_lead_category",
        "description": "AI-generated summary of the call conversation",
    },
]


async def create_custom_fields() -> None:
    """Create all custom fields in Frappe CRM."""
    settings = get_settings()

    if not settings.frappe_url:
        print("ERROR: FRAPPE_URL not configured in .env")
        sys.exit(1)

    base_url = settings.frappe_url.rstrip("/")
    headers = {
        "Authorization": f"token {settings.frappe_api_key}:{settings.frappe_api_secret}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    print("=" * 50)
    print("  Frappe CRM — Custom Field Setup")
    print("=" * 50)
    print(f"  Instance: {base_url}")
    print()

    async with httpx.AsyncClient(timeout=15) as client:
        # Verify connection first
        try:
            resp = await client.get(
                f"{base_url}/api/method/frappe.auth.get_logged_user",
                headers=headers,
            )
            resp.raise_for_status()
            user = resp.json().get("message", "unknown")
            print(f"  Connected as: {user}")
            print()
        except Exception as e:
            print(f"ERROR: Cannot connect to Frappe — {e}")
            sys.exit(1)

        # Create each custom field
        created = 0
        skipped = 0

        for field_def in CUSTOM_FIELDS:
            fieldname = field_def["fieldname"]
            label = field_def["label"]

            # Check if field already exists
            try:
                check_url = (
                    f"{base_url}/api/resource/Custom Field"
                    f"?filters=[[\"dt\",\"=\",\"{field_def['dt']}\"],"
                    f"[\"fieldname\",\"=\",\"{fieldname}\"]]"
                    f"&limit_page_length=1"
                )
                resp = await client.get(check_url, headers=headers)
                resp.raise_for_status()
                existing = resp.json().get("data", [])

                if existing:
                    print(f"  ⏭  {label} ({fieldname}) — already exists")
                    skipped += 1
                    continue

            except Exception:
                pass  # Proceed to create

            # Create the field
            try:
                field_data = {
                    "doctype": "Custom Field",
                    **field_def,
                }

                resp = await client.post(
                    f"{base_url}/api/resource/Custom Field",
                    headers=headers,
                    json=field_data,
                )
                resp.raise_for_status()
                print(f"  ✅  {label} ({fieldname}) — created")
                created += 1

            except Exception as e:
                print(f"  ❌  {label} ({fieldname}) — FAILED: {e}")

        print()
        print(f"  Done! Created: {created}, Skipped: {skipped}")
        print("=" * 50)


if __name__ == "__main__":
    asyncio.run(create_custom_fields())
