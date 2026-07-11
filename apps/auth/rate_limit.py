"""
Fixed-window rate limiting for unauthenticated auth endpoints (register,
login, forgot-password, reset-password) - the ones an attacker can hit
without already holding a valid token, making them the targets for
brute-forcing or account enumeration.

Backed by Redis (atomic INCR + EXPIRE) rather than an in-memory counter, so
the limit holds correctly across multiple app processes/instances, not just
within a single one. Each counter key expires on its own after the window,
so it "resets" naturally without any separate cleanup logic.
"""
from fastapi import HTTPException, Request, status

from libs.shared.redis_client import client as redis_client

MAX_ATTEMPTS = 4
WINDOW_SECONDS = 15 * 60


def _client_identifier(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(endpoint: str):
    """FastAPI dependency factory: `dependencies=[Depends(rate_limit("login"))]`."""

    def _dependency(request: Request) -> None:
        identifier = _client_identifier(request)
        key = f"rate_limit:{endpoint}:{identifier}"
        # INCR creates the key at 1 if absent; only arm its expiry on that
        # first hit so a still-live counter's window isn't pushed back out.
        attempts = redis_client.incr(key)
        if attempts == 1:
            redis_client.expire(key, WINDOW_SECONDS)

        if attempts > MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many attempts. Try again in up to {WINDOW_SECONDS // 60} minutes.",
            )

    return _dependency
