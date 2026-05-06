"""Agent Bus Tool — Redis pub/sub for agent-to-agent messaging."""
from crewai.tools import BaseTool
from pydantic import Field
from typing import Optional
import json


class AgentBusTool(BaseTool):
    name: str = Field(default="AgentBus")
    description: str = (
        "Send a message to another agent or receive messages. "
        "Use to: request_info (ask another agent for information), "
        "provide_info (send results back), task_complete (notify completion). "
        "Format: send to='AgentName' action='research_request' data={...} "
        "Or recv timeout=30 to wait for a response."
    )

    def _run(self, action: str = "send", to: str = "", from_: str = "", data: str = "{}",
             timeout: int = 30, recv_agent: str = "CMO") -> str:
        """Run the AgentBus tool.
        
        Args:
            action: 'send' or 'recv'
            to: Recipient agent name (for send)
            from_: Sender agent name (for send) — this is WHO IS CALLING (the sender)
            data: JSON payload (for send)
            timeout: Seconds to wait for recv
            recv_agent: Agent name to subscribe as for recv (the RECEIVER's channel)
        """
        from src.agent_bus import AgentBus
        bus = AgentBus()

        if action == "send":
            # 'from_' is the SENDER — who is calling this tool
            try:
                parsed = json.loads(data) if isinstance(data, str) and data.startswith("{") else {}
            except (json.JSONDecodeError, ValueError):
                parsed = {"raw": data}
            msg_id = bus.send(to=to, from_=from_, action=action, data=parsed)
            return f"Message sent: {msg_id}"
        elif action == "recv":
            # recv_agent is THIS agent — subscribe to its own channel
            # The message's 'from' field tells us who sent it
            bus = AgentBus()
            msg = bus.recv(agent_name=recv_agent, timeout=timeout)
            if msg:
                return json.dumps(msg, indent=2)
            return "No message received."
        return "Unknown action. Use send or recv."
