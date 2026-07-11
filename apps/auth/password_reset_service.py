"""Forgot-password token generation and redemption."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status

from apps.auth.email_service import send_password_reset_email
from apps.auth.user_service import get_user_by_email, update_password
from libs.shared.db import password_reset_tokens_collection

RESET_TOKEN_EXPIRE_MINUTES = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def create_reset_token(email: str) -> Optional[str]:
    """
    Emails a one-time reset link to `email` if it matches a user, and returns
    the raw token (only ever available here - only its hash is stored).
    Silently no-ops if the email doesn't match any user, so the caller can
    return the same response either way and avoid leaking which emails are
    registered.
    """
    user = get_user_by_email(email)
    if user is None:
        return None

    raw_token = secrets.token_urlsafe(32)
    password_reset_tokens_collection.insert_one({
        "token_hash": _hash_token(raw_token),
        "user_id": user["_id"],
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES),
        "used": False,
    })
    send_password_reset_email(user["email"], raw_token, RESET_TOKEN_EXPIRE_MINUTES)
    return raw_token


def reset_password(token: str, new_password: str) -> None:
    record = password_reset_tokens_collection.find_one({"token_hash": _hash_token(token)})
    if record is None or record["used"] or _as_aware(record["expires_at"]) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

    update_password(record["user_id"], new_password)
    password_reset_tokens_collection.update_one({"_id": record["_id"]}, {"$set": {"used": True}})
