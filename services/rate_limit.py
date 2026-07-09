"""
Fixed-window rate limiting for unauthenticated auth endpoints (register,
login, forgot-password, reset-password) - the ones an attacker can hit
without already holding a valid token, making them the targets for
brute-forcing or account enumeration.

Backed by MongoDB (like revoked_tokens/password_reset_tokens) rather than an
in-memory counter, so the limit holds correctly across multiple app
processes/instances, not just within a single one.
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status

from services.db import rate_limit_attempts_collection

MAX_ATTEMPTS = 4
WINDOW_SECONDS = 15 * 60


def _client_identifier(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(endpoint: str):
    """FastAPI dependency factory: `dependencies=[Depends(rate_limit("login"))]`."""

    def _dependency(request: Request) -> None:
        identifier = _client_identifier(request)
        attempts = rate_limit_attempts_collection.count_documents({
            "identifier": identifier,
            "endpoint": endpoint,
        })
        if attempts >= MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many attempts. Try again in up to {WINDOW_SECONDS // 60} minutes.",
            )

        now = datetime.now(timezone.utc)
        rate_limit_attempts_collection.insert_one({
            "identifier": identifier,
            "endpoint": endpoint,
            "created_at": now,
            "expires_at": now + timedelta(seconds=WINDOW_SECONDS),
        })

    return _dependency
