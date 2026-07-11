"""Basic stdlib logging setup, shared by both services - no extra dependency.

Called once at import time by each service's app.py, before any other
first-party module (so anything logged during subsequent imports, e.g. a
startup failure, is still formatted/emitted correctly).
"""
import logging
import os

# Optional - unlike the required settings in config.py, a missing/invalid
# LOG_LEVEL isn't a misconfiguration worth failing startup over, so this one
# genuinely defaults rather than using config.py's _require().
_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


def configure_logging() -> None:
    logging.basicConfig(
        level=_LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
