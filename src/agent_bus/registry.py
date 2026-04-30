"""Agent registry — manages agent registration in Redis Hash."""

import json
import time
import threading
from typing import Any

from .redis_client import get_redis

_AGENT_KEY_PREFIX = "agent:"
_HEARTBEAT_INTERVAL = 30.0  # seconds


class AgentRegistry:
    """Manages agent registration and heartbeat in Redis."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis = get_redis(redis_url)
        self._heartbeat_thread: threading.Thread | None = None

    def register(self, role: str, metadata: dict[str, Any]) -> None:
        """Register an agent role in Redis, marking it online."""
        key = f"{_AGENT_KEY_PREFIX}{role}"
        data = {
            "role": role,
            "pid": metadata.get("pid", ""),
            "started_at": time.time(),
            "heartbeat": time.time(),
            "status": "online",
            "metadata": json.dumps(metadata),
        }
        self.redis.hset(key, mapping=data)

    def unregister(self, role: str) -> None:
        """Remove an agent registration."""
        key = f"{_AGENT_KEY_PREFIX}{role}"
        self.redis.delete(key)

    def is_online(self, role: str) -> bool:
        """Check if an agent is currently online (has heartbeat within 2x interval)."""
        key = f"{_AGENT_KEY_PREFIX}{role}"
        raw = self.redis.hget(key, "heartbeat")
        if raw is None:
            return False
        try:
            hb = float(raw)
            return (time.time() - hb) < (_HEARTBEAT_INTERVAL * 2)
        except (ValueError, TypeError):
            return False

    def list_online_agents(self) -> list[str]:
        """Return roles of all currently online agents."""
        keys = self.redis.keys(f"{_AGENT_KEY_PREFIX}*")
        online = []
        now = time.time()
        for key in keys:
            if key.endswith(":inbox") or key.endswith(":pending"):
                continue
            raw = self.redis.hget(key, "heartbeat")
            if raw:
                try:
                    hb = float(raw)
                    if (now - hb) < (_HEARTBEAT_INTERVAL * 2):
                        role = self.redis.hget(key, "role")
                        if role:
                            online.append(role)
                except (ValueError, TypeError):
                    pass
        return online

    def start_heartbeat(self, role: str) -> None:
        """Start a background thread that sends heartbeats every HEARTBEAT_INTERVAL."""
        def beat():
            key = f"{_AGENT_KEY_PREFIX}{role}"
            while True:
                self.redis.hset(key, "heartbeat", time.time())
                time.sleep(_HEARTBEAT_INTERVAL)

        self._heartbeat_thread = threading.Thread(target=beat, daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        """Stop the heartbeat thread."""
        self._heartbeat_thread = None