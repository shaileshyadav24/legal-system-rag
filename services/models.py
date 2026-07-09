"""Request/response models for the auth, chat, and query endpoints."""
from typing import Optional

from pydantic import BaseModel, EmailStr


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class QueryRequest(BaseModel):
    query: str
    collection_name: Optional[str] = None
    session_id: Optional[str] = None
