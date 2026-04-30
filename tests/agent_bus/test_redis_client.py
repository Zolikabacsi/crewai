"""Tests for redis_client.py."""

from src.agent_bus.redis_client import get_redis, reset_client


def test_get_redis_returns_redis_object():
    r = get_redis()
    assert r is not None
    assert callable(getattr(r, "ping", None))


def test_get_redis_returns_same_instance():
    r1 = get_redis()
    r2 = get_redis()
    assert r1 is r2


def test_reset_clears_client():
    reset_client()
    r1 = get_redis()
    reset_client()
    r2 = get_redis()
    # After reset they are different objects (new connections)
    assert r1 is not None
    assert r2 is not None
