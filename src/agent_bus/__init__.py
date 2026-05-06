"""Agent Message Bus — Redis pub/sub for agent-to-agent communication.

Usage:
    # Agent A sends a message to Agent B:
    from src.agent_bus import AgentBus
    bus = AgentBus()
    bus.send(to="CFO", from_="BusinessAssistant", action="provide_info", data={"query": "...", "result": "..."})

    # Agent B listens for messages:
    bus = AgentBus()
    msg = bus.recv(agent_name="CFO", timeout=30)
    if msg:
        print(f"From {msg['from']}: {msg['action']} — {msg['data']}")
"""
from src.agent_bus.message_bus import AgentBus

__all__ = ["AgentBus"]
