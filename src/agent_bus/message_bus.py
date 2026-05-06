"""Agent Message Bus — Redis pub/sub for agent-to-agent communication.

Architecture:
- Each agent has its own Redis channel: `agent.{agent_name}`
- Broadcast channel: `agent.broadcast` for discovery/announcements
- Messages are JSON dicts with: from, to, action, data, timestamp
- Messages are also written to a Redis Stream for durability when agents are offline
"""

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional
import redis


REDIS_HOST = "localhost"
REDIS_PORT = 6379
AGENT_CHANNEL_PREFIX = "agent."
BROADCAST_CHANNEL = "agent.broadcast"
STREAM_KEY = "agent_stream"


class AgentBus:
    """Redis pub/sub message bus for agent-to-agent communication.
    
    Send a message:
        bus = AgentBus()
        bus.send(to="CFO", from_="BusinessAssistant", action="research_request", data={"query": "..."})
    
    Receive a message (blocking):
        bus = AgentBus()
        msg = bus.recv(agent_name="CFO", timeout=30)
        if msg:
            print(f"From: {msg['from']} | Action: {msg['action']} | Data: {msg['data']}")
    
    Non-blocking poll:
        msg = bus.recv_nowait(agent_name="CFO")
    
    Broadcast:
        bus.broadcast(from_="CFO", action="report_ready", data={"summary": "..."})
    """

    def __init__(self, host: str = REDIS_HOST, port: int = REDIS_PORT):
        self.host = host
        self.port = port
        self._redis = redis.Redis(host=host, port=port, decode_responses=True, socket_connect_timeout=5)
        self._pubsub: Optional[redis.client.PubSub] = None

    def _channel(self, agent_name: str) -> str:
        return f"{AGENT_CHANNEL_PREFIX}{agent_name}"

    def _build_msg(self, to: str, from_: str, action: str, data: Optional[dict]) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "from": from_,
            "to": to,
            "action": action,
            "data": data or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def send(
        self,
        to: str,
        from_: str,
        action: str,
        data: Optional[dict] = None,
    ) -> str:
        """Send a message to an agent or broadcast channel.
        
        Uses Redis PUBLISH (fire-and-forget pub/sub).
        Also writes to Redis Stream for durability.
        
        Args:
            to: Recipient agent name, or "BROADCAST" for all agents
            from_: Sender agent name  
            action: Message type (e.g. "research_request", "provide_info", "task_complete")
            data: Message payload
        
        Returns:
            message_id: UUID of the message
        """
        msg = self._build_msg(to, from_, action, data)
        msg_json = json.dumps(msg)
        channel = self._channel(to) if to != "BROADCAST" else BROADCAST_CHANNEL

        # Publish to channel (real-time delivery to active listeners)
        self._redis.publish(channel, msg_json)
        
        # Also write to stream (durable, survives listener downtime)
        try:
            self._redis.xadd(STREAM_KEY, {
                "id": msg["id"],
                "from": msg["from"],
                "to": msg["to"],
                "action": msg["action"],
                "data": json.dumps(msg["data"]),
                "timestamp": msg["timestamp"],
            }, maxlen=5000, approximate=True)
        except redis.exceptions.ResponseError:
            # Stream not available (Redis version < 5), skip
            pass

        return msg["id"]

    def recv(
        self,
        agent_name: str,
        timeout: int = 30,
    ) -> Optional[dict]:
        """Receive a message addressed to this agent (blocking).
        
        Subscribes to agent channel and waits for messages.
        Also checks stream for messages received while no active listener.
        
        Args:
            agent_name: This agent's name
            timeout: Seconds to wait for a message (0 = non-blocking)
        
        Returns:
            Message dict, or None if timeout reached
        """
        channel = self._channel(agent_name)
        
        # First: check stream for messages delivered while we weren't listening (non-blocking)
        stream_msgs = self._read_stream(agent_name, count=10)
        if stream_msgs:
            return stream_msgs[0]

        # Second: blocking pub/sub subscription
        pubsub = self._redis.pubsub()
        try:
            pubsub.subscribe(channel, BROADCAST_CHANNEL)

            while True:
                msg = pubsub.get_message(timeout=timeout)
                if msg is None:
                    return None
                if msg["type"] != "message":
                    continue

                try:
                    data = json.loads(msg["data"])
                    # Only accept messages addressed to us or broadcast
                    if data.get("to") == agent_name or data.get("to") == "BROADCAST":
                        return data
                except (json.JSONDecodeError, KeyError):
                    continue
        finally:
            try:
                pubsub.unsubscribe(channel, BROADCAST_CHANNEL)
                pubsub.close()
            except Exception:
                pass

    def recv_nowait(self, agent_name: str) -> Optional[dict]:
        """Non-blocking check for messages.
        
        Checks stream first, then pub/sub queue.
        """
        # Check stream
        stream_msgs = self._read_stream(agent_name, count=5)
        if stream_msgs:
            return stream_msgs[0]
        
        # Check pubsub queue (non-blocking)
        if self._pubsub is None:
            self._pubsub = self._redis.pubsub()
            self._pubsub.subscribe(self._channel(agent_name), BROADCAST_CHANNEL)
        
        msg = self._pubsub.get_message(timeout=0)
        if msg and msg["type"] == "message":
            try:
                data = json.loads(msg["data"])
                if data.get("to") == agent_name or data.get("to") == "BROADCAST":
                    return data
            except (json.JSONDecodeError, KeyError):
                pass
        return None

    def _read_stream(self, agent_name: str, count: int = 10,
                     block_ms: int | None = None) -> list[dict]:
        """Read messages from stream addressed to this agent.

        Tracks last-read ID per agent in Redis so each message is processed exactly once.
        Pass block_ms to do a blocking wait for new messages (used by recv()).
        Without block_ms, only returns already-queued messages immediately.
        """
        # Per-agent cursor stored as a Redis string key
        cursor_key = f"stream_cursor:{agent_name}"
        last_id = self._redis.get(cursor_key) or "0"

        messages = []
        try:
            if block_ms is not None:
                results = self._redis.xread(
                    {STREAM_KEY: last_id}, count=count, block=block_ms
                )
            else:
                results = self._redis.xread(
                    {STREAM_KEY: last_id}, count=count
                )
        except redis.exceptions.ResponseError:
            return messages

        if not results:
            return messages

        for stream_name, msgs in results:
            for msg_id, msg_data in msgs:
                msg_to = msg_data.get("to", "")
                if msg_to == agent_name or msg_to == "BROADCAST":
                    # Delete it so it's not processed again
                    try:
                        self._redis.xdel(STREAM_KEY, msg_id)
                    except Exception:
                        pass
                    try:
                        data_str = msg_data.get("data", "{}")
                        data = json.loads(data_str) if isinstance(data_str, str) else data_str
                    except json.JSONDecodeError:
                        data = {}
                    messages.append({
                        "id": msg_data.get("id"),
                        "from": msg_data.get("from"),
                        "to": msg_data.get("to"),
                        "action": msg_data.get("action"),
                        "data": data,
                        "timestamp": msg_data.get("timestamp"),
                    })
            # Update cursor to after the last msg in this batch
            if msgs:
                last_msg_id = msgs[-1][0]
                self._redis.set(cursor_key, last_msg_id)

        return messages

    def broadcast(
        self,
        from_: str,
        action: str,
        data: Optional[dict] = None,
    ) -> str:
        """Send a broadcast message to all agents."""
        return self.send(to="BROADCAST", from_=from_, action=action, data=data)

    def ping(self) -> bool:
        """Check if Redis is reachable."""
        try:
            return self._redis.ping()
        except Exception:
            return False

    # ── Agent Registration (shared with agent_bus.agent_bus.AgentBus) ──────

    _heartbeat_thread: Optional[threading.Thread] = None
    _heartbeat_role: Optional[str] = None
    _heartbeat_interval = 30.0  # seconds between renewals

    def register(self, role: str, metadata: Optional[dict] = None) -> None:
        """Register this agent with Redis, marking it online with a heartbeat.

        Uses the same key scheme as agent_bus.agent_bus.AgentBus so both
        can see each other's registration: key = f"agent:{role}"
        """
        self._heartbeat_role = role
        key = f"agent:{role}"
        data = {
            "heartbeat": str(time.time()),
            "pid": metadata.get("pid", os.getpid()) if metadata else os.getpid(),
            "type": metadata.get("type", "unknown") if metadata else "unknown",
        }
        self._redis.hset(key, mapping=data)
        # Expire in 5 minutes — heartbeat must be renewed or agent goes offline
        self._redis.expire(key, 300)

    def start_heartbeat(self, role: str) -> None:
        """Start a background thread that renews the registration every 30s."""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._heartbeat_role = role

        def tick():
            while True:
                time.sleep(self._heartbeat_interval)
                try:
                    key = f"agent:{self._heartbeat_role}"
                    self._redis.hset(key, "heartbeat", str(time.time()))
                    self._redis.expire(key, 300)
                except Exception:
                    pass

        self._heartbeat_thread = threading.Thread(target=tick, daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        if self._heartbeat_thread:
            self._heartbeat_role = None
            self._heartbeat_thread = None

    def is_online(self, role: str) -> bool:
        """Check if an agent is currently online (has a valid heartbeat in Redis)."""
        key = f"agent:{role}"
        return self._redis.exists(key) == 1

    def unregister(self, role: str) -> None:
        """Unregister an agent, removing its online status."""
        key = f"agent:{role}"
        self._redis.delete(key)
