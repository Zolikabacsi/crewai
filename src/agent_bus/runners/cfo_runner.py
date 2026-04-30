"""Startup wrapper for the CFO agent — run in its own tmux process.

Usage:
  tmux new-session -d -s cfo_agent "cd ~/srv/crewai && source .venv/bin/activate && python src/agent_bus/runners/cfo_runner.py"
"""

import atexit
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.agent_bus import AgentBus
from src.agents.agents import CFOPartner


def main():
    bus = AgentBus()

    def handle(payload: str) -> str:
        agent = CFOPartner()
        # The agent.invoke() method is not defined on CrewAI Agent instances.
        # Use the agent's native method to execute the task.
        # For CrewAI agents, we invoke the underlying LLM directly:
        result = agent.agent_executor.invoke({"input": payload})
        return str(result.get("output", result))

    atexit.register(bus.unregister)

    print("CFO agent starting...")
    bus.start(role="CFO", handler=handle)


if __name__ == "__main__":
    main()
