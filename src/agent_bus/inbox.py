"""InboxPoller — blocking read from a Redis list inbox."""

from .redis_client import get_redis
from .models import Message


class InboxPoller:
    """Wraps BRPOP for blocking inbox reads from a Redis list."""

    DEFAULT_TIMEOUT = 5.0  # seconds per poll cycle

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis = get_redis(redis_url)

    def pop(self, inbox_key: str, timeout: float = DEFAULT_TIMEOUT) -> Message | None:
        """Blocking pop from inbox. Returns Message or None on timeout."""
        result = self.redis.brpop(inbox_key, timeout=timeout)
        if result is None:
            return None
        # brpop returns (key, value) tuple
        _, raw = result
        return Message.from_json(raw)

    def push(self, inbox_key: str, message: Message) -> None:
        """Push a message onto an inbox (LPUSH)."""
        self.redis.lpush(inbox_key, message.to_json())
