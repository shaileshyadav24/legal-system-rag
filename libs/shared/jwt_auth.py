"""JWT issuing/verification and the current-user dependency. Shared by both services: the auth service issues tokens, the chat service only ever verifies them."""
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from libs.shared.config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET
from libs.shared.db import users_collection
from libs.shared.redis_client import client as redis_client

_REVOKED_TOKEN_KEY_PREFIX = "revoked_token:"

_bearer_scheme = HTTPBearer()


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    # jti gives each token an identity independent of its (sub, exp) pair, so
    # logout can revoke this one token without needing to store the token itself.
    payload = {"sub": user_id, "exp": expire, "jti": uuid.uuid4().hex}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


def is_token_revoked(jti: str) -> bool:
    return redis_client.exists(f"{_REVOKED_TOKEN_KEY_PREFIX}{jti}") == 1


def revoke_token(jti: str, expires_at_timestamp: float) -> None:
    # TTL = the token's own remaining lifetime, so the key self-cleans once
    # the token would've expired anyway (matches the old Mongo TTL-index behavior).
    ttl_seconds = max(int(expires_at_timestamp - time.time()), 1)
    redis_client.set(f"{_REVOKED_TOKEN_KEY_PREFIX}{jti}", "1", ex=ttl_seconds)


def get_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> Dict[str, Any]:
    payload = decode_access_token(credentials.credentials)
    if is_token_revoked(payload.get("jti", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")
    return payload


def get_current_user(payload: Dict[str, Any] = Depends(get_token_payload)) -> Dict[str, Any]:
    try:
        user_id = ObjectId(payload["sub"])
    except (KeyError, InvalidId) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        ) from exc

    user = users_collection.find_one({"_id": user_id})
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
