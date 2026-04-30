"""Startup wrapper for the CEO agent — run in its own tmux process.

Usage:
  tmux new-session -d -s ceo_agent "cd ~/srv/crewai && source .venv/bin/activate && python src/agent_bus/runners/ceo_runner.py"
"""

import atexit
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.agent_bus import AgentBus
from src.agents.agents import CEOPartner


def main():
    bus = AgentBus()

    def handle(payload: str) -> str:
        agent = CEOPartner()
        result = agent.agent_executor.invoke({"input": payload})
        return str(result.get("output", result))

    atexit.register(bus.unregister)

    print("CEO agent starting...")
    bus.start(role="CEO", handler=handle)


if __name__ == "__main__":
    main()
