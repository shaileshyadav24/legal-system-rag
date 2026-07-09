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
from services.rate_limit import rate_limit
from services.user_service import authenticate_user, create_user, to_user_out

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token, dependencies=[Depends(rate_limit("register"))])
def register(request: UserRegister) -> Dict[str, Any]:
    user = create_user(request)
    token = create_access_token(str(user["_id"]))
    return {"access_token": token, "user": to_user_out(user)}


@router.post("/login", response_model=Token, dependencies=[Depends(rate_limit("login"))])
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


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(rate_limit("forgot-password"))])
def forgot_password(request: ForgotPasswordRequest) -> None:
    # Always the same response regardless of whether the email matched a user
    # (create_reset_token no-ops for an unknown email), so the response itself
    # never reveals which emails are registered. The reset link only ever
    # reaches the user via the email sent in create_reset_token.
    create_reset_token(request.email)


@router.post(
    "/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("reset-password"))],
)
def do_reset_password(request: ResetPasswordRequest) -> None:
    reset_password(request.token, request.new_password)
