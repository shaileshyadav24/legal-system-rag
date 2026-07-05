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
