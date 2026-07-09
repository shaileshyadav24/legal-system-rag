"""Environment-driven settings for MongoDB and JWT auth."""
import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} environment variable must be set (see .env.example)")
    return value


MONGODB_URI = _require("MONGODB_URI")
MONGODB_DB_NAME = _require("MONGODB_DB_NAME")

JWT_SECRET = _require("JWT_SECRET")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(_require("JWT_EXPIRE_MINUTES"))

RESEND_API_KEY = _require("RESEND_API_KEY")
RESEND_FROM_EMAIL = _require("RESEND_FROM_EMAIL")
# Base URL of the FE's reset-password page; the raw token is appended as
# `?token=...` when building the link sent in the reset email.
PASSWORD_RESET_URL = _require("PASSWORD_RESET_URL")
