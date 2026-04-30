"""AgentBus — main class for inter-agent messaging via Redis."""

import os
import time
import uuid
from typing import Callable

from .redis_client import get_redis
from .models import Message, AgentTimeoutError, AgentOfflineError, AgentNotFoundError
from .registry import AgentRegistry
from .inbox import InboxPoller

_REDIS_URL_DEFAULT = os.getenv("AGENT_BUS_REDIS_URL", "redis://localhost:6379/0")
_INBOX_KEY_PREFIX = "agent:"
_PENDING_KEY_PREFIX = "agent:pending:"
_TASK_KEY_PREFIX = "agent:tasks:"
_DEFAULT_TIMEOUT = 30.0
_TASK_TTL = 300  # 5 minutes


class AgentBus:
    """Redis-backed message bus for inter-agent communication.

    Usage (receiver/agent process):
        bus = AgentBus()
        bus.register(role="CFO", metadata={"pid": os.getpid()})
        def handler(payload: str) -> str:
            return cfo_agent.analyse(payload)
        bus.start(role="CFO", handler=handler)   # blocks forever

    Usage (caller):
        bus = AgentBus()
        result = bus.call("CFO", "analyse this financial model")
    """

    def __init__(self, redis_url: str = _REDIS_URL_DEFAULT):
        self.redis = get_redis(redis_url)
        self.registry = AgentRegistry(redis_url)
        self.poller = InboxPoller(redis_url)
        self._my_role: str | None = None
        # Default anonymous inbox used by callers that haven't registered yet
        self._my_inbox_key: str = f"{_INBOX_KEY_PREFIX}anonymous:{uuid.uuid4().hex[:8]}:inbox"

    # ── Registration ────────────────────────────────────────────────────

    def register(self, role: str, metadata: dict) -> None:
        """Register this agent with Redis. Call once on startup."""
        self._my_role = role
        self._my_inbox_key = f"{_INBOX_KEY_PREFIX}{role}:inbox"
        self.registry.register(role, metadata)
        self.registry.start_heartbeat(role)

    def unregister(self) -> None:
        """Unregister this agent. Call on shutdown."""
        if self._my_role:
            self.registry.unregister(self._my_role)
            self.registry.stop_heartbeat()
            self._my_role = None
            self._my_inbox_key = None

    # ── Startup loop ───────────────────────────────────────────────────

    def start(self, role: str, handler: Callable[[str], str]) -> None:
        """Register and enter the blocking poll loop.

        This method blocks indefinitely. It processes incoming messages
        and calls `handler(payload) -> response` for each one.
        """
        self.register(role=role, metadata={"pid": os.getpid()})

        # Flush pending queue before entering the main loop
        self._flush_pending_queue(role)

        inbox = f"{_INBOX_KEY_PREFIX}{role}:inbox"
        while True:
            msg = self.poller.pop(inbox, timeout=5.0)
            if msg is None:
                continue
            if msg.msg_type == "request":
                try:
                    response = handler(msg.payload)
                except Exception as e:
                    response = f"[ERROR] {type(e).__name__}: {e}"
                reply = Message(
                    task_id=msg.task_id,
                    sender=role,
                    payload=response,
                    msg_type="response",
                    reply_to=None,
                )
                if msg.reply_to:
                    self.poller.push(msg.reply_to, reply)

    def _flush_pending_queue(self, role: str) -> None:
        """Process any requests that arrived while this agent was offline."""
        pending_key = f"{_PENDING_KEY_PREFIX}{role}"
        while True:
            raw = self.redis.rpop(pending_key)
            if raw is None:
                break
            msg = Message.from_json(raw)
            # Re-inject into the agent's inbox as a new request
            inbox = f"{_INBOX_KEY_PREFIX}{role}:inbox"
            self.redis.lpush(inbox, msg.to_json())

    # ── Outbound calls ──────────────────────────────────────────────────

    def call(self, role: str, payload: str, timeout: float = _DEFAULT_TIMEOUT) -> str:
        """Send a message to another agent and wait for a response (sync)."""
        if not self.registry.is_online(role):
            self._queue_pending(role, payload, self._my_inbox_key)
            raise AgentOfflineError(f"Agent '{role}' is not online. Request queued.")

        task_id = str(uuid.uuid4())
        msg = Message(
            task_id=task_id,
            sender=self._my_role or "unknown",
            payload=payload,
            msg_type="request",
            reply_to=self._my_inbox_key,
        )
        self.redis.lpush(f"{_INBOX_KEY_PREFIX}{role}:inbox", msg.to_json())

        # Block on own inbox waiting for response
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = deadline - time.time()
            result = self.redis.brpop(self._my_inbox_key, timeout=int(remaining))
            if result:
                _, raw = result
                response_msg = Message.from_json(raw)
                if response_msg.task_id == task_id:
                    return response_msg.payload
            time.sleep(0.1)

        raise AgentTimeoutError(f"Timed out after {timeout}s waiting for {role}")

    def call_async(self, role: str, payload: str) -> str:
        """Send a message and return immediately with a task_id (async)."""
        task_id = str(uuid.uuid4())
        msg = Message(
            task_id=task_id,
            sender=self._my_role or "unknown",
            payload=payload,
            msg_type="request",
            reply_to=self._my_inbox_key,
        )
        if not self.registry.is_online(role):
            self._queue_pending(role, payload, self._my_inbox_key, task_id)
            return task_id  # queued, caller should await_result later

        self.redis.lpush(f"{_INBOX_KEY_PREFIX}{role}:inbox", msg.to_json())
        self.redis.set(f"{_TASK_KEY_PREFIX}{task_id}", "", ex=_TASK_TTL)
        return task_id

    def await_result(self, task_id: str, timeout: float = _DEFAULT_TIMEOUT) -> str:
        """Wait for an async call result by task_id."""
        inbox = self._my_inbox_key
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = deadline - time.time()
            result = self.redis.brpop(inbox, timeout=int(remaining))
            if result:
                _, raw = result
                msg = Message.from_json(raw)
                if msg.task_id == task_id and msg.msg_type == "response":
                    return msg.payload
            time.sleep(0.1)
        raise AgentTimeoutError(f"Timed out waiting for async result {task_id}")

    def broadcast(self, event: str, payload: str) -> None:
        """Broadcast a one-way event to all listening agents."""
        import json
        self.redis.publish("agent.events", json.dumps({
            "event": event,
            "payload": payload,
            "sender": self._my_role or "unknown",
        }))

    def is_online(self, role: str) -> bool:
        """Check if an agent is currently online."""
        return self.registry.is_online(role)

    def list_online_agents(self) -> list[str]:
        """List all currently online agent roles."""
        return self.registry.list_online_agents()

    # ── Internal helpers ────────────────────────────────────────────────

    def _queue_pending(self, role: str, payload: str, reply_to: str | None, task_id: str | None = None) -> None:
        """Queue a request for an agent that is currently offline."""
        tid = task_id or str(uuid.uuid4())
        msg = Message(
            task_id=tid,
            sender=self._my_role or "unknown",
            payload=payload,
            msg_type="request",
            reply_to=reply_to,
        )
        self.redis.lpush(f"{_PENDING_KEY_PREFIX}{role}", msg.to_json())
