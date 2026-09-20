"""Small, opt-in authentication helpers for HTTP and voice endpoints."""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from app.config import get_settings


async def require_api_token(authorization: str | None = Header(default=None)) -> None:
    """Require a bearer token when API_AUTH_TOKEN is configured."""
    expected = get_settings().api_auth_token
    if not expected:
        return

    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
