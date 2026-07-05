"""FastAPI routes for registration, login, logout, and password management."""
from typing import Any, Dict

from fastapi import APIRouter, Depends, status

from services.auth import create_access_token, get_current_user, get_token_payload, revoke_token
from services.models import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    Token,
    UserLogin,
    UserOut,
    UserRegister,
)
from services.password_reset_service import create_reset_token, reset_password
from services.user_service import authenticate_user, create_user, to_user_out

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token)
def register(request: UserRegister) -> Dict[str, Any]:
    user = create_user(request)
    token = create_access_token(str(user["_id"]))
    return {"access_token": token, "user": to_user_out(user)}


@router.post("/login", response_model=Token)
def login(request: UserLogin) -> Dict[str, Any]:
    user = authenticate_user(request.email, request.password)
    token = create_access_token(str(user["_id"]))
    return {"access_token": token, "user": to_user_out(user)}


@router.get("/me", response_model=UserOut)
def me(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return to_user_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: Dict[str, Any] = Depends(get_token_payload)) -> None:
    revoke_token(payload["jti"], payload["exp"])


@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest) -> Dict[str, Any]:
    token = create_reset_token(request.email)
    # Always return the same shape/message regardless of whether the email
    # matched a user, so the response itself doesn't reveal which emails are
    # registered. The token is echoed back only because no email delivery is
    # wired up yet - in production this would be emailed, never returned here.
    return {
        "detail": "If an account with that email exists, a password reset token has been generated.",
        "reset_token": token,
    }


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def do_reset_password(request: ResetPasswordRequest) -> None:
    reset_password(request.token, request.new_password)
