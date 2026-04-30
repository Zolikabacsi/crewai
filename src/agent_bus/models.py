"""Data models and exceptions for AgentBus."""

from dataclasses import dataclass, field
from typing import Any
import time
import json


@dataclass
class Message:
    task_id: str
    sender: str          # role of the calling agent
    payload: str         # the actual content
    msg_type: str        # "request" | "response" | "event"
    reply_to: str | None # inbox key to reply to
    created_at: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps({
            "task_id": self.task_id,
            "sender": self.sender,
            "payload": self.payload,
            "msg_type": self.msg_type,
            "reply_to": self.reply_to,
            "created_at": self.created_at,
        })

    @classmethod
    def from_json(cls, raw: str) -> "Message":
        d = json.loads(raw)
        return cls(**d)


class AgentBusError(Exception):
    """Base exception for AgentBus errors."""
    pass


class AgentTimeoutError(AgentBusError):
    """Sync call timed out waiting for response."""
    pass


class AgentOfflineError(AgentBusError):
    """Target agent is not currently online."""
    pass


class AgentNotFoundError(AgentBusError):
    """No agent registered with that role."""
    pass


class RedisConnectionError(AgentBusError):
    """Cannot connect to Redis."""
    pass
