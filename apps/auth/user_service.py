"""CRUD and authentication logic for the users collection."""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from apps.auth.models import UserRegister
from apps.auth.password_auth import hash_password, verify_password
from libs.shared.db import users_collection


def create_user(request: UserRegister) -> Dict[str, Any]:
    user = {
        "email": request.email.lower(),
        "hashed_password": hash_password(request.password),
        "full_name": request.full_name,
        "role": "user",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        result = users_collection.insert_one(user)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc
    user["_id"] = result.inserted_id
    return user


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    return users_collection.find_one({"email": email.lower()})


def authenticate_user(email: str, password: str) -> Dict[str, Any]:
    user = get_user_by_email(email)
    if user is None or not verify_password(password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    return user


def update_password(user_id: ObjectId, new_password: str) -> None:
    users_collection.update_one({"_id": user_id}, {"$set": {"hashed_password": hash_password(new_password)}})


def to_user_out(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
    }
