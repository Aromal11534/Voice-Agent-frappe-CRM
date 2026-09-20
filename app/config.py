"""
Application configuration loaded from environment variables.

Uses pydantic-settings to validate and type-check all config values at startup.
Copy .env.example to .env and fill in your credentials before running.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All application configuration in one place."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Exotel ──────────────────────────────────────────────
    exotel_sid: str = ""
    exotel_api_key: str = ""
    exotel_api_token: str = ""
    exotel_phone: str = ""  # ExoPhone number
    exotel_base_url: str = "https://api.in.exotel.com"

    # ── Sarvam AI ───────────────────────────────────────────
    sarvam_api_key: str = ""
    sarvam_stt_model: str = "saaras:v3-realtime"
    sarvam_tts_model: str = "bulbul:v3"
    sarvam_tts_voice: str = "shubh"

    # ── Sarvam conversational LLM ───────────────────────────
    # One Sarvam subscription key powers STT, LLM, and TTS.
    llm_model: str = "sarvam-105b-conversations"

    # ── Frappe CRM ──────────────────────────────────────────
    # PostgreSQL Database
    database_url: str = "postgresql://voiceagent:secretpassword@localhost:5434/voiceagent"

    # Frappe CRM Integration
    frappe_url: str = ""
    frappe_api_key: str = ""
    frappe_api_secret: str = ""

    # ── Application ─────────────────────────────────────────
    server_url: str = "http://localhost:8000"  # Public URL for Exotel callbacks
    log_level: str = "INFO"
    api_auth_token: str = ""
    cors_origins: str = "http://localhost:5173"
    dashboard_user: str = "hello@hashadz.com"
    dashboard_password: str = "HasHadz@435@#*22asd"


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — settings are loaded once at startup."""
    return Settings()


def is_configured(*values: str) -> bool:
    """Return false for empty values and placeholders shipped in .env.example."""
    placeholder_prefixes = ("your_", "replace_", "changeme", "xxx")
    return all(
        value and not value.strip().lower().startswith(placeholder_prefixes)
        for value in values
    )
