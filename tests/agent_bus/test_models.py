"""Tests for Message dataclass and exceptions."""

import json
import time
from src.agent_bus.models import Message, AgentBusError, AgentTimeoutError


def test_message_to_json_roundtrips():
    msg = Message(
        task_id="abc123",
        sender="CEO",
        payload="analyse this",
        msg_type="request",
        reply_to="agent:CEO:inbox",
    )
    restored = Message.from_json(msg.to_json())
    assert restored.task_id == "abc123"
    assert restored.sender == "CEO"
    assert restored.payload == "analyse this"
    assert restored.msg_type == "request"
    assert restored.reply_to == "agent:CEO:inbox"


def test_message_created_at_defaults_to_now():
    before = time.time()
    msg = Message(task_id="x", sender="A", payload="p", msg_type="req", reply_to=None)
    after = time.time()
    assert before <= msg.created_at <= after


def test_exception_hierarchy():
    assert issubclass(AgentTimeoutError, AgentBusError)
