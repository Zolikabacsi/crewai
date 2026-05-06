"""Startup wrapper for the OfficeAssistant agent — run in its own process.

Usage:
  cd ~/srv/crewai && source .venv/bin/activate && python src/agent_bus/runners/office_assistant_runner.py
"""

import atexit
import os
import sys

# Change to the crewai directory 
os.chdir('/home/zoltan/srv/crewai')

# Add paths properly - the src directory is a package
sys.path.insert(0, '/home/zoltan/srv/crewai')
sys.path.insert(0, '/home/zoltan/srv/crewai/src')

from src.agent_bus.agent_bus import AgentBus
from src.agents.office_assistant import OfficeAssistant


def main():
    bus = AgentBus()

    def handle(payload: str) -> str:
        agent = OfficeAssistant()
        result = agent.agent_executor.invoke({"input": payload})
        return str(result.get("output", result))

    atexit.register(bus.unregister)

    print("OfficeAssistant starting...")
    bus.start(role="office_assistant", handler=handle)


if __name__ == "__main__":
    main()
