"""Integration tests for AgentBus using a real Redis instance."""

import threading
import time
import pytest
from src.agent_bus.agent_bus import AgentBus
from src.agent_bus.models import AgentOfflineError, AgentTimeoutError


@pytest.fixture
def bus():
    b = AgentBus()
    b.redis.flushdb()   # clean slate
    yield b
    b.unregister()


def test_sync_call_between_two_threads(bus):
    """CEO calls CFO, CFO responds."""
    def fake_cfo_handler(payload: str) -> str:
        return f"CFO processed: {payload}"

    # Start CFO in a background thread (simulates tmux process)
    cfo_bus = AgentBus()
    t = threading.Thread(target=cfo_bus.start, args=("CFO", fake_cfo_handler), daemon=True)
    t.start()
    time.sleep(1.5)   # let CFO register and flush its pending queue

    # CEO calls CFO
    result = bus.call("CFO", "analyse this model", timeout=10.0)
    assert result == "CFO processed: analyse this model"
    cfo_bus.unregister()


def test_async_call_returns_task_id_immediately(bus):
    """call_async returns immediately; await_result waits for the response."""
    cfo_bus = AgentBus()
    cfo_bus.redis.flushdb()   # isolate from prior test's shared inbox

    def fake_cfo(payload: str) -> str:
        return "done"

    t = threading.Thread(target=cfo_bus.start, args=("CFO_ASYNC", fake_cfo), daemon=True)
    t.start()
    time.sleep(1.5)

    task_id = bus.call_async("CFO_ASYNC", "quick check")
    assert task_id is not None
    assert len(task_id) == 36  # uuid4 length

    result = bus.await_result(task_id, timeout=10.0)
    assert result == "done"
    cfo_bus.unregister()


def test_offline_agent_queues_request(bus):
    """When CFO is offline, call should queue and succeed when CFO starts."""
    task_id = bus.call_async("CFO_OFFLINE_TEST", "do something")
    assert task_id is not None

    # Simulate CFO starting up and processing the queue
    cfo_bus = AgentBus()
    def handler(p: str) -> str:
        return f"handled: {p}"
    t = threading.Thread(target=cfo_bus.start, args=("CFO_OFFLINE_TEST", handler), daemon=True)
    t.start()
    time.sleep(2.0)   # CFO registers, flushes queue, processes

    result = bus.await_result(task_id, timeout=10.0)
    assert result == "handled: do something"
    cfo_bus.unregister()


def test_sync_call_offline_raises_error(bus):
    with pytest.raises(AgentOfflineError):
        bus.call("DEFINITELY_OFFLINE", "test", timeout=1.0)


def test_is_online(bus):
    cfo_bus = AgentBus()
    def h(p): return p
    t = threading.Thread(target=cfo_bus.start, args=("CFO_ONLINE_TEST", h), daemon=True)
    t.start()
    time.sleep(1.5)
    assert bus.is_online("CFO_ONLINE_TEST") is True
    cfo_bus.unregister()
    time.sleep(2.0)
    assert bus.is_online("CFO_ONLINE_TEST") is False
