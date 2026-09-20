"""
FastAPI application entry point.

Run with:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import close_db, init_db
from app.routes import router
from app.routes_dashboard import router as dashboard_router


def _setup_logging() -> None:
    """Configure structured, readable logging for the application."""
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Format: clean, human-readable logs that also look good in demos
    fmt = "%(asctime)s | %(levelname)-7s | %(name)-25s | %(message)s"
    date_fmt = "%H:%M:%S"

    logging.basicConfig(
        level=log_level,
        format=fmt,
        datefmt=date_fmt,
        stream=sys.stdout,
        force=True,
    )

    # Quiet down noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle events."""
    _setup_logging()
    logger = logging.getLogger("app.main")

    # Initialize PostgreSQL database
    await init_db()
    logger.info("  Database      : PostgreSQL initialized")

    settings = get_settings()
    logger.info("=" * 60)
    logger.info("  AI Voice Agent + Frappe CRM")
    logger.info("=" * 60)
    logger.info(f"  Server URL    : {settings.server_url}")
    logger.info(f"  LLM Model     : {settings.llm_model}")
    logger.info(f"  STT Model     : {settings.sarvam_stt_model}")
    logger.info(f"  TTS Model     : {settings.sarvam_tts_model}")
    logger.info(f"  Frappe CRM    : {settings.frappe_url or '(not configured)'}")
    logger.info(f"  Exotel SID    : {settings.exotel_sid or '(not configured)'}")
    logger.info("=" * 60)

    yield  # Application runs here

    logger.info("Shutting down AI Voice Agent")
    await close_db()


# ── Create Application ──────────────────────────────────────

app = FastAPI(
    title="AI Voice Agent + Frappe CRM",
    description=(
        "An AI-powered voice agent that handles incoming and outgoing phone calls "
        "in Malayalam and English, conducts sales conversations, and saves "
        "structured lead data to Frappe CRM."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — permissive for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in get_settings().cors_origins.split(",")
        if origin.strip()
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routes
app.include_router(router)
app.include_router(dashboard_router)
