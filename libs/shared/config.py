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

REDIS_URL = _require("REDIS_URL")

# Comma-separated list of origins allowed to call either service from a
# browser, e.g. "https://app.example.com,https://staging.example.com" - no
# wildcard support on purpose, since both apps also set allow_credentials=True
# and browsers reject a wildcard Access-Control-Allow-Origin on credentialed
# requests.
ALLOWED_ORIGINS = [origin.strip() for origin in _require("ALLOWED_ORIGINS").split(",") if origin.strip()]

JWT_SECRET = _require("JWT_SECRET")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(_require("JWT_EXPIRE_MINUTES"))

RESEND_API_KEY = _require("RESEND_API_KEY")
RESEND_FROM_EMAIL = _require("RESEND_FROM_EMAIL")
# Base URL of the FE's reset-password page; the raw token is appended as
# `?token=...` when building the link sent in the reset email.
PASSWORD_RESET_URL = _require("PASSWORD_RESET_URL")

# Base URL of the Ollama server the chat service generates answers with
# (e.g. "http://localhost:11434" locally, or an in-cluster Ollama service
# address in a real deployment). Only used by the chat service, but lives
# here like RESEND_*/PASSWORD_RESET_URL above - the auth service still needs
# it set in its environment for this module to import successfully.
OLLAMA_HOST = _require("OLLAMA_HOST")
# Name of the Ollama model to generate answers with, e.g. "tinyllama" - must
# already be pulled on the OLLAMA_HOST server (`ollama pull <model>`). Only
# used by the chat service; same reasoning as OLLAMA_HOST above for why it
# lives in this shared module.
OLLAMA_MODEL = _require("OLLAMA_MODEL")
