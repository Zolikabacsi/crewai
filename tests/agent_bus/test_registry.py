"""Tests for AgentRegistry."""

import time
import pytest
from src.agent_bus.registry import AgentRegistry


@pytest.fixture
def registry():
    r = AgentRegistry()
    r.register("test_agent", {"pid": 12345})
    yield r
    r.unregister("test_agent")


def test_register_then_is_online(registry):
    assert registry.is_online("test_agent") is True


def test_unregister_then_is_offline(registry):
    registry.unregister("test_agent")
    assert registry.is_online("test_agent") is False


def test_list_online_agents(registry):
    registry.register("test_agent_2", {"pid": 99999})
    online = registry.list_online_agents()
    assert "test_agent" in online
    assert "test_agent_2" in online
    registry.unregister("test_agent_2")


def test_is_online_false_for_unknown_role(registry):
    assert registry.is_online("nonexistent_role") is False