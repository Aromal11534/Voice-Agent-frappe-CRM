"""
Frappe CRM REST API client.

Provides async methods to interact with Frappe CRM:
  - Find leads by phone number
  - Create new leads
  - Update existing leads
  - Add comments (call summaries)
  - Create follow-up ToDo items
"""

from __future__ import annotations

import logging
import json
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class FrappeClient:
    """Async HTTP client for Frappe CRM REST API."""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.frappe_url.rstrip("/")
        self.headers = {
            "Authorization": f"token {settings.frappe_api_key}:{settings.frappe_api_secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _url(self, path: str) -> str:
        """Build full API URL."""
        return f"{self.base_url}/api/resource/{path}"

    def _method_url(self, method: str) -> str:
        """Build full URL for frappe.client methods."""
        return f"{self.base_url}/api/method/{method}"

    async def find_lead_by_phone(self, phone: str) -> dict[str, Any] | None:
        """
        Search for an existing CRM Lead by phone number.

        Returns the lead dict if found, None otherwise.
        Searches both 'phone' and 'mobile_no' fields.
        """
        # Normalize phone: strip spaces, ensure consistent format
        phone_clean = phone.strip().replace(" ", "")

        filters = [
            ["mobile_no", "like", f"%{phone_clean[-10:]}%"],
        ]

        params = {
            "filters": json.dumps(filters),
            "fields": '["name"]',
            "limit_page_length": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    self._url("CRM Lead"),
                    headers=self.headers,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])

                if data:
                    logger.info(f"FRAPPE  Lead found: {data[0].get('name')}")
                    return data[0]

                logger.info("FRAPPE  No existing lead found")
                return None

        except Exception:
            logger.exception("FRAPPE  Error searching for lead")
            raise

    async def create_lead(self, lead_data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Create a new CRM Lead in Frappe.

        Args:
            lead_data: Dict with lead fields (first_name, mobile_no, etc.)

        Returns:
            Created lead dict or None on failure.
        """
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    self._url("CRM Lead"),
                    headers=self.headers,
                    json=lead_data,
                )
                resp.raise_for_status()
                result = resp.json().get("data", {})
                lead_name = result.get("name", "unknown")
                logger.info(f"FRAPPE  Lead created: {lead_name}")
                return result

        except Exception:
            logger.exception("FRAPPE  Error creating lead")
            return None

    async def create_call_log(self, log_data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Create a CRM Call Log record in Frappe.
        """
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    self._url("CRM Call Log"),
                    headers=self.headers,
                    json=log_data,
                )
                resp.raise_for_status()
                result = resp.json().get("data", {})
                log_name = result.get("name", "unknown")
                logger.info(f"FRAPPE  Call Log created: {log_name}")
                return result
        except Exception:
            logger.exception("FRAPPE  Error creating Call Log")
            return None

    async def create_deal(self, deal_data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a CRM Deal record in Frappe."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    self._url("CRM Deal"),
                    headers=self.headers,
                    json=deal_data,
                )
                resp.raise_for_status()
                result = resp.json().get("data", {})
                deal_name = result.get("name", "unknown")
                logger.info(f"FRAPPE  Deal created: {deal_name}")
                return result
        except Exception:
            logger.exception("FRAPPE  Error creating Deal")
            return None

    async def get_call_logs_by_lead(self, lead_name: str) -> list[str]:
        """Get all CRM Call Logs linked to a lead."""
        try:
            filters = [["reference_docname", "=", lead_name]]
            params = {
                "filters": json.dumps(filters),
                "fields": '["name"]',
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    self._url("CRM Call Log"),
                    headers=self.headers,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])
                return [d["name"] for d in data]
        except Exception:
            return []

    async def delete_document(self, doctype: str, docname: str) -> bool:
        """Delete a document in Frappe."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.delete(
                    self._url(f"{doctype}/{docname}"),
                    headers=self.headers,
                )
                resp.raise_for_status()
                logger.info(f"FRAPPE  Deleted {doctype}: {docname}")
                return True
        except Exception:
            logger.exception(f"FRAPPE  Error deleting {doctype}/{docname}")
            return False

    async def update_lead(
        self, lead_name: str, update_data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        Update an existing CRM Lead.

        Args:
            lead_name: The Frappe document name (e.g., "CRM-LEAD-00001")
            update_data: Dict of fields to update.
        """
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.put(
                    self._url(f"CRM Lead/{lead_name}"),
                    headers=self.headers,
                    json=update_data,
                )
                resp.raise_for_status()
                result = resp.json().get("data", {})
                logger.info(f"FRAPPE  Lead updated: {lead_name}")
                return result

        except Exception:
            logger.exception(f"FRAPPE  Error updating lead {lead_name}")
            return None

    async def add_comment(
        self, doctype: str, docname: str, comment: str
    ) -> dict[str, Any] | None:
        """
        Add a comment (call summary) to a Frappe document.

        Uses frappe.client.add_comment API method.
        """
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    self._method_url("frappe.client.add_comment"),
                    headers=self.headers,
                    json={
                        "reference_doctype": doctype,
                        "reference_name": docname,
                        "content": comment,
                        "comment_type": "Comment",
                    },
                )
                resp.raise_for_status()
                logger.info(f"FRAPPE  Comment added to {doctype}/{docname}")
                return resp.json().get("message")

        except Exception:
            logger.exception("FRAPPE  Error adding comment")
            return None

    async def create_note(
        self, content: str, reference_doctype: str, reference_name: str
    ) -> dict[str, Any] | None:
        """Create an FCRM Note and attach it to a document."""
        note_data = {
            "doctype": "FCRM Note",
            "title": "AI Call Summary",
            "content": content,
            "reference_doctype": reference_doctype,
            "reference_docname": reference_name
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    self._url("FCRM Note"),
                    headers=self.headers,
                    json=note_data,
                )
                resp.raise_for_status()
                logger.info(f"FRAPPE  Note added to {reference_doctype}/{reference_name}")
                return resp.json().get("data")
        except Exception:
            logger.exception("FRAPPE  Error creating Note")
            return None

    async def create_todo(
        self,
        description: str,
        reference_type: str = "",
        reference_name: str = "",
        assigned_to: str = "",
    ) -> dict[str, Any] | None:
        """
        Create a follow-up ToDo item in Frappe.

        Args:
            description: The task description.
            reference_type: Link to a DocType (e.g., "CRM Lead").
            reference_name: Link to a specific document.
            assigned_to: Email of the assignee (optional).
        """
        todo_data: dict[str, Any] = {
            "doctype": "ToDo",
            "description": description,
            "status": "Open",
            "priority": "Medium",
        }

        if reference_type and reference_name:
            todo_data["reference_type"] = reference_type
            todo_data["reference_name"] = reference_name

        if assigned_to:
            todo_data["allocated_to"] = assigned_to

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    self._url("ToDo"),
                    headers=self.headers,
                    json=todo_data,
                )
                resp.raise_for_status()
                result = resp.json().get("data", {})
                todo_name = result.get("name", "unknown")
                logger.info(f"FRAPPE  ToDo created: {todo_name}")
                return result

        except Exception:
            logger.exception("FRAPPE  Error creating ToDo")
            return None

    async def check_connection(self) -> bool:
        """Verify connectivity to Frappe instance."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    self._method_url("frappe.auth.get_logged_user"),
                    headers=self.headers,
                )
                resp.raise_for_status()
                user = resp.json().get("message", "")
                logger.info(f"FRAPPE  Connected as: {user}")
                return True
        except Exception:
            logger.exception("FRAPPE  Connection check failed")
            return False
