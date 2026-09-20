import unittest
from unittest.mock import AsyncMock, patch

from app.models.schemas import ExtractedLead, LeadCategory, TranscriptEntry
from app.services.crm import _build_lead_fields, process_call_to_crm


class CrmMappingTests(unittest.TestCase):
    def test_extracted_lead_maps_to_frappe_fields(self):
        lead = ExtractedLead(
            name="Anu Nair",
            phone="+919876543210",
            language="Malayalam + English",
            intent="Website Development",
            requirement="A multilingual storefront",
            budget=150000,
            timeline="6 weeks",
            lead_status=LeadCategory.HOT,
            summary="Qualified lead.",
            follow_up_required=True,
        )
        fields = _build_lead_fields(lead)
        self.assertEqual(fields["first_name"], "Anu")
        self.assertEqual(fields["last_name"], "Nair")
        self.assertEqual(fields["custom_lead_category"], "Hot")
        self.assertEqual(fields["custom_budget"], 150000)


class CrmPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_mode_extracts_without_syncing_to_frappe(self):
        lead = ExtractedLead(phone="browser-simulator", summary="Test call")
        transcript = [TranscriptEntry(role="caller", text="Hello")]

        with (
            patch("app.services.crm.extract_lead_info", AsyncMock(return_value=lead)),
            patch("app.services.crm.save_extraction", AsyncMock()) as save_extraction,
            patch("app.services.crm._save_to_frappe", AsyncMock()) as save_to_frappe,
        ):
            result = await process_call_to_crm(
                transcript,
                "browser-simulator",
                db_call_id=1,
                sync_to_frappe=False,
            )

        self.assertEqual(result, lead)
        save_extraction.assert_awaited_once()
        save_to_frappe.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
