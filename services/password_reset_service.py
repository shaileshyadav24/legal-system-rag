"""Forgot-password token generation and redemption."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status

from services.db import password_reset_tokens_collection
from services.user_service import get_user_by_email, update_password

RESET_TOKEN_EXPIRE_MINUTES = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def create_reset_token(email: str) -> Optional[str]:
    """
    Returns the raw one-time reset token if `email` matches a user, else None.
    Only the token's hash is stored, so this is the only place the raw value
    is ever available - in production it should be emailed to the user rather
    than returned to the caller (no email delivery is wired up yet).
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
    return raw_token


def reset_password(token: str, new_password: str) -> None:
    record = password_reset_tokens_collection.find_one({"token_hash": _hash_token(token)})
    if record is None or record["used"] or _as_aware(record["expires_at"]) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

    update_password(record["user_id"], new_password)
    password_reset_tokens_collection.update_one({"_id": record["_id"]}, {"$set": {"used": True}})
