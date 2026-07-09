"""Password hashing, JWT issuing/verification, and the current-user dependency."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import bcrypt
import jwt
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET
from services.db import revoked_tokens_collection, users_collection

_bearer_scheme = HTTPBearer()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


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
    return revoked_tokens_collection.find_one({"jti": jti}) is not None


def revoke_token(jti: str, expires_at_timestamp: float) -> None:
    revoked_tokens_collection.update_one(
        {"jti": jti},
        {"$setOnInsert": {"expires_at": datetime.fromtimestamp(expires_at_timestamp, tz=timezone.utc)}},
        upsert=True,
    )


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
