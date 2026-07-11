"""Owns the single Redis client, used for JWT revocation and auth rate limiting."""
import redis

from libs.shared.config import REDIS_URL

client = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def ensure_connection() -> None:
    """
    Fail fast with a clear error if Redis isn't reachable, instead of letting
    the first real read/write fail deep inside some other call path (e.g. the
    first login attempt after deploy).
    """
    try:
        client.ping()
    except redis.RedisError as exc:
        raise RuntimeError(
            f"Could not connect to Redis at {REDIS_URL!r}. "
            "Check that Redis is running/reachable and REDIS_URL is correct."
        ) from exc
