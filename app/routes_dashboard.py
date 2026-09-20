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

from app.database import get_call_detail, get_call_stats, get_recent_calls
from app.security import require_api_token

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_api_token)])

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
