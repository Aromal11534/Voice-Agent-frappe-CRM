"""
PostgreSQL database layer for call storage.

Stores call logs, transcripts, and AI extraction results in PostgreSQL
using asyncpg for async operations.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import asyncpg

from app.config import get_settings

logger = logging.getLogger(__name__)


# ── Schema ──────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS calls (
    id              SERIAL PRIMARY KEY,
    call_sid        TEXT UNIQUE,
    caller_number   TEXT,
    direction       TEXT DEFAULT 'inbound',
    start_time      TIMESTAMP,
    end_time        TIMESTAMP,
    duration_sec    INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'in_progress',
    detected_lang   TEXT DEFAULT 'auto',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transcripts (
    id              SERIAL PRIMARY KEY,
    call_id         INTEGER REFERENCES calls(id),
    role            TEXT NOT NULL,
    text            TEXT NOT NULL,
    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS extractions (
    id              SERIAL PRIMARY KEY,
    call_id         INTEGER REFERENCES calls(id) UNIQUE,
    extracted_data  JSONB,
    lead_status     TEXT,
    frappe_synced   INTEGER DEFAULT 0,
    frappe_lead_name TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_calls_caller ON calls(caller_number);
CREATE INDEX IF NOT EXISTS idx_calls_start ON calls(start_time);
CREATE INDEX IF NOT EXISTS idx_transcripts_call ON transcripts(call_id);
CREATE INDEX IF NOT EXISTS idx_extractions_call ON extractions(call_id);
"""

# Global connection pool
_pool = None


def _require_pool():
    if _pool is None:
        raise RuntimeError("Database pool is not initialized")
    return _pool

async def init_db() -> None:
    """Initialize the database and create tables if they don't exist."""
    global _pool
    settings = get_settings()
    
    try:
        # Create connection pool
        _pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=10)
        
        async with _pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
            
        logger.info("DATABASE  PostgreSQL connection pool initialized")
    except Exception as e:
        logger.error(f"DATABASE  Failed to initialize PostgreSQL: {e}")
        raise

async def close_db() -> None:
    """Close the database pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def check_db() -> bool:
    """Return whether the database pool can execute a simple query."""
    try:
        pool = _require_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval("SELECT 1") == 1
    except Exception:
        return False


# ── Call Operations ─────────────────────────────────────────


async def save_call_start(
    call_sid: str,
    caller_number: str,
    direction: str = "inbound",
) -> int:
    """Record the start of a new call. Returns the database call ID."""
    global _pool
    async with _require_pool().acquire() as conn:
        call_id = await conn.fetchval(
            """
            INSERT INTO calls (call_sid, caller_number, direction, start_time, status)
            VALUES ($1, $2, $3, $4, 'in_progress')
            RETURNING id
            """,
            call_sid, caller_number, direction, datetime.now()
        )
        logger.info(f"DATABASE  Call started -- ID: {call_id}, SID: {call_sid}")
        return call_id


async def save_call_end(call_id: int, duration_sec: int = 0) -> None:
    """Record the end of a call."""
    global _pool
    async with _require_pool().acquire() as conn:
        await conn.execute(
            """
            UPDATE calls
            SET end_time = $1, duration_sec = $2, status = 'completed'
            WHERE id = $3
            """,
            datetime.now(), duration_sec, call_id
        )
        logger.info(f"DATABASE  Call ended -- ID: {call_id}, Duration: {duration_sec}s")


# ── Transcript Operations ──────────────────────────────────


async def save_transcript_entry(
    call_id: int,
    role: str,
    text: str,
) -> None:
    """Save a single transcript turn (caller or agent)."""
    global _pool
    async with _require_pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO transcripts (call_id, role, text, timestamp)
            VALUES ($1, $2, $3, $4)
            """,
            call_id, role, text, datetime.now()
        )


# ── Extraction Operations ──────────────────────────────────


async def save_extraction(
    call_id: int,
    extracted_data: dict[str, Any],
    lead_status: str = "",
) -> None:
    """Save the LLM extraction result for a call."""
    global _pool
    async with _require_pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO extractions (call_id, extracted_data, lead_status)
            VALUES ($1, $2, $3)
            ON CONFLICT (call_id) DO UPDATE 
            SET extracted_data = EXCLUDED.extracted_data, lead_status = EXCLUDED.lead_status
            """,
            call_id, json.dumps(extracted_data, ensure_ascii=False), lead_status
        )
        logger.info(f"DATABASE  Extraction saved -- Call ID: {call_id}, Status: {lead_status}")


async def mark_frappe_synced(
    call_id: int,
    lead_name: str,
) -> None:
    """Mark an extraction as successfully synced to Frappe CRM."""
    global _pool
    async with _require_pool().acquire() as conn:
        await conn.execute(
            """
            UPDATE extractions
            SET frappe_synced = 1, frappe_lead_name = $1
            WHERE call_id = $2
            """,
            lead_name, call_id
        )
        logger.info(f"DATABASE  Frappe sync confirmed -- Call ID: {call_id}, Lead: {lead_name}")


# ── Query Operations (for Dashboard API) ───────────────────────


async def get_recent_calls(limit: int = 20) -> list[dict[str, Any]]:
    """Get recent calls with extraction summary."""
    global _pool
    async with _require_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                c.id, c.call_sid, c.caller_number, c.direction,
                c.start_time, c.end_time, c.duration_sec, c.status,
                c.detected_lang,
                e.lead_status, e.frappe_synced, e.frappe_lead_name,
                e.extracted_data
            FROM calls c
            LEFT JOIN extractions e ON e.call_id = c.id
            ORDER BY c.start_time DESC
            LIMIT $1
            """,
            limit
        )

        results = []
        for row in rows:
            item = dict(row)
            # Convert datetime to ISO string for JSON serialization
            if item.get("start_time"): item["start_time"] = item["start_time"].isoformat()
            if item.get("end_time"): item["end_time"] = item["end_time"].isoformat()
            
            # extracted_data is already a string (JSONB returned as string by asyncpg depending on config, but we'll parse it)
            if item.get("extracted_data") and isinstance(item["extracted_data"], str):
                try:
                    item["extracted_data"] = json.loads(item["extracted_data"])
                except json.JSONDecodeError:
                    pass
            results.append(item)

        return results


async def get_call_detail(call_id: int) -> dict[str, Any] | None:
    """Get full call detail including transcript and extraction."""
    global _pool
    async with _require_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT c.*, e.extracted_data, e.lead_status,
                   e.frappe_synced, e.frappe_lead_name
            FROM calls c
            LEFT JOIN extractions e ON e.call_id = c.id
            WHERE c.id = $1
            """,
            call_id
        )
        if not row:
            return None

        call = dict(row)
        if call.get("start_time"): call["start_time"] = call["start_time"].isoformat()
        if call.get("end_time"): call["end_time"] = call["end_time"].isoformat()
        if call.get("created_at"): call["created_at"] = call["created_at"].isoformat()

        if call.get("extracted_data") and isinstance(call["extracted_data"], str):
            try:
                call["extracted_data"] = json.loads(call["extracted_data"])
            except json.JSONDecodeError:
                pass

        # Get transcript
        transcript_rows = await conn.fetch(
            """
            SELECT role, text, timestamp
            FROM transcripts
            WHERE call_id = $1
            ORDER BY timestamp ASC
            """,
            call_id
        )
        
        transcript = []
        for r in transcript_rows:
            tr = dict(r)
            if tr.get("timestamp"): tr["timestamp"] = tr["timestamp"].isoformat()
            transcript.append(tr)
            
        call["transcript"] = transcript

        return call


async def get_call_stats() -> dict[str, Any]:
    """Get aggregate statistics for the dashboard."""
    global _pool
    async with _require_pool().acquire() as conn:
        # Total calls
        total_calls = await conn.fetchval("SELECT COUNT(*) FROM calls")

        # Calls by direction
        dir_rows = await conn.fetch("SELECT direction, COUNT(*) FROM calls GROUP BY direction")
        by_direction = {row["direction"]: row["count"] for row in dir_rows}

        # Calls by status
        status_rows = await conn.fetch("SELECT status, COUNT(*) FROM calls GROUP BY status")
        by_status = {row["status"]: row["count"] for row in status_rows}

        # Lead categories
        lead_rows = await conn.fetch(
            """
            SELECT lead_status, COUNT(*) 
            FROM extractions 
            WHERE lead_status IS NOT NULL AND lead_status != ''
            GROUP BY lead_status
            """
        )
        by_lead_status = {row["lead_status"]: row["count"] for row in lead_rows}

        # Frappe sync stats
        sync_row = await conn.fetchrow("SELECT COALESCE(SUM(frappe_synced), 0) as synced, COUNT(*) as total FROM extractions")
        frappe_synced = sync_row["synced"]
        frappe_total = sync_row["total"]

        # Average duration
        avg_dur = await conn.fetchval("SELECT AVG(duration_sec) FROM calls WHERE status = 'completed'")
        avg_duration = round(float(avg_dur or 0), 1)

        # Today's calls
        today_calls = await conn.fetchval(
            "SELECT COUNT(*) FROM calls WHERE DATE(start_time) = CURRENT_DATE"
        )

        return {
            "total_calls": total_calls,
            "today_calls": today_calls,
            "by_direction": by_direction,
            "by_status": by_status,
            "by_lead_status": by_lead_status,
            "frappe_synced": frappe_synced,
            "frappe_pending": frappe_total - frappe_synced,
            "avg_duration_sec": avg_duration,
        }

async def delete_all_history() -> None:
    """Delete all calls, transcripts, and extractions from the database."""
    global _pool
    async with _require_pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM extractions")
            await conn.execute("DELETE FROM transcripts")
            await conn.execute("DELETE FROM calls")
        logger.info("DATABASE  All history deleted")

async def get_all_frappe_lead_names() -> list[str]:
    """Get all synced frappe lead names to delete them from CRM."""
    global _pool
    async with _require_pool().acquire() as conn:
        rows = await conn.fetch("SELECT frappe_lead_name FROM extractions WHERE frappe_synced = 1 AND frappe_lead_name IS NOT NULL")
        return [row["frappe_lead_name"] for row in rows]
