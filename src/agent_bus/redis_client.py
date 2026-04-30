"""Redis connection singleton with automatic reconnection."""

import redis
import time
from typing import Optional

_redis_client: Optional[redis.Redis] = None
_REDIS_URL_DEFAULT = "redis://localhost:6379/0"
_MAX_RETRIES = 5


def get_redis(url: str = _REDIS_URL_DEFAULT) -> redis.Redis:
    """Return a shared Redis client, creating it on first call.

    Handles reconnection with exponential backoff on connection loss.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = _connect(url)
    return _redis_client


def _connect(url: str) -> redis.Redis:
    """Connect to Redis with up to MAX_RETRIES retries."""
    client = redis.from_url(url, decode_responses=True)
    for attempt in range(_MAX_RETRIES):
        try:
            client.ping()
            return client
        except redis.ConnectionError as e:
            if attempt == _MAX_RETRIES - 1:
                raise redis.ConnectionError(f"Failed to connect after {_MAX_RETRIES} attempts") from e
            wait = 2 ** attempt
            time.sleep(wait)
    raise redis.ConnectionError("Connection failed")


def reset_client() -> None:
    """Reset the shared client (useful for testing)."""
    global _redis_client
    if _redis_client is not None:
        _redis_client.close()
        _redis_client = None
