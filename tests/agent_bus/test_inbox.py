"""Tests for InboxPoller."""

import pytest
from src.agent_bus.inbox import InboxPoller
from src.agent_bus.models import Message


INBOX = "agent:test_inbox_poller:inbox"


@pytest.fixture(autouse=True)
def clean_inbox():
    """Ensure a clean Redis inbox before and after each test."""
    from src.agent_bus.redis_client import get_redis
    r = get_redis()
    r.delete(INBOX)
    yield
    r.delete(INBOX)


@pytest.fixture
def poller():
    return InboxPoller()


def test_push_then_pop(poller):
    msg = Message(
        task_id="t1",
        sender="CEO",
        payload="hello",
        msg_type="request",
        reply_to="agent:CEO:inbox",
    )
    poller.push(INBOX, msg)
    result = poller.pop(INBOX, timeout=2.0)
    assert result is not None
    assert result.task_id == "t1"
    assert result.payload == "hello"


def test_pop_returns_none_on_timeout(poller):
    result = poller.pop(INBOX, timeout=0.5)
    assert result is None


def test_multiple_messages(poller):
    for i in range(3):
        msg = Message(
            task_id=f"t{i}",
            sender="A",
            payload=f"msg{i}",
            msg_type="request",
            reply_to=None,
        )
        poller.push(INBOX, msg)
    # LPUSH + BRPOP = FIFO (first-in-first-out):
    # LPUSH adds to head, BRPOP removes from tail.
    first = poller.pop(INBOX, timeout=1.0)
    assert first.task_id == "t0"
    second = poller.pop(INBOX, timeout=1.0)
    assert second.task_id == "t1"
