"""
Dashboard API routes -- serves JSON API for the React frontend.

Endpoints:
  GET /api/calls          -- recent calls list (JSON)
  GET /api/calls/{id}     -- call detail with transcript (JSON)
  GET /api/stats          -- aggregate stats (JSON)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.database import get_call_detail, get_call_stats, get_recent_calls, delete_all_history, get_all_frappe_lead_names
from app.integrations.frappe import FrappeClient
from app.security import require_api_token
from app.config import get_settings
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_api_token)])
auth_router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str

@auth_router.post("/api/auth/login", tags=["auth"])
async def api_login(req: LoginRequest):
    settings = get_settings()
    if req.email == settings.dashboard_user and req.password == settings.dashboard_password:
        return {"token": settings.api_auth_token}
    return JSONResponse(status_code=401, content={"error": "Invalid credentials"})

# ── Dashboard API ───────────────────────────────────────────


@router.get("/api/calls", tags=["dashboard"])
async def api_calls(limit: int = Query(default=20, ge=1, le=100)):
    """Get recent calls with extraction summaries."""
    try:
        calls = await get_recent_calls(limit=limit)
        return JSONResponse(content={"calls": calls})
    except Exception:
        logger.exception("DASHBOARD  Error fetching calls")
        return JSONResponse(content={"calls": [], "error": "Failed to fetch calls"}, status_code=500)


@router.get("/api/calls/{call_id}", tags=["dashboard"])
async def api_call_detail(call_id: int):
    """Get full detail for a specific call including transcript."""
    try:
        detail = await get_call_detail(call_id)
        if not detail:
            return JSONResponse(content={"error": "Call not found"}, status_code=404)
        return JSONResponse(content={"call": detail})
    except Exception:
        logger.exception(f"DASHBOARD  Error fetching call {call_id}")
        return JSONResponse(content={"error": "Failed to fetch call"}, status_code=500)


@router.get("/api/stats", tags=["dashboard"])
async def api_stats():
    """Get aggregate call statistics."""
    try:
        stats = await get_call_stats()
        return JSONResponse(content=stats)
    except Exception:
        logger.exception("DASHBOARD  Error fetching stats")
        return JSONResponse(content={"error": "Failed to fetch stats"}, status_code=500)


@router.delete("/api/calls", tags=["dashboard"])
async def api_delete_calls():
    """Delete all call history."""
    try:
        lead_names = await get_all_frappe_lead_names()
        if lead_names:
            frappe = FrappeClient()
            for lead_name in lead_names:
                call_logs = await frappe.get_call_logs_by_lead(lead_name)
                for cl in call_logs:
                    await frappe.delete_document("CRM Call Log", cl)
                await frappe.delete_document("CRM Lead", lead_name)

        await delete_all_history()
        return JSONResponse(content={"success": True})
    except Exception:
        logger.exception("DASHBOARD  Error deleting calls")
        return JSONResponse(content={"error": "Failed to delete history"}, status_code=500)
