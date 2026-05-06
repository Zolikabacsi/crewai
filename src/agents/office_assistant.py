"""Office Assistant agent — calendar, email, vault, Drive sync."""

from crewai import Agent
from crewai.llm import LLM
from ..config import Config
from ..tools import (
    CalendarTool,
    EmailSearchTool,
    VaultSearchTool,
    VaultReadTool,
    DriveSyncTool,
)
from ..agent_storage import VaultStorageTool


def get_llm():
    return LLM(
        provider="anthropic",
        model="MiniMax-M2.7",
        api_key=Config.ANTHROPIC_AUTH_TOKEN,
        base_url=Config.ANTHROPIC_BASE_URL,
    )


class OfficeAssistant(Agent):
    def __init__(self):
        super().__init__(
            role="Office & Calendar Assistant",
            goal=(
                "Provide accurate, real-time answers about your schedule, "
                "email context, and company documents. Maintain vault sync with Drive."
            ),
            backstory=(
                "You are a diligent executive assistant with access to Google Calendar, "
                "Gmail, and the company document vault. You answer questions precisely, "
                "maintain strict privacy, and run a daily check to keep the vault up to "
                "date with new Drive files. "
                "When you complete research tasks, use VaultStorageTool to save findings to the vault "
                "and AgentBus to communicate findings back to requesting agents."
            ),
            verbose=Config.VERBOSE,
            tools=[
                CalendarTool(),
                EmailSearchTool(),
                VaultSearchTool(),
                VaultReadTool(),
                DriveSyncTool(),
                VaultStorageTool(agent_folder="BusinessAssistant", sub_folder="office_docs"),
            ],
            llm=get_llm(),
        )
        # Add AgentBusTool via lazy import to avoid circular deps
        from src.tools import AgentBusTool
        self.tools.append(AgentBusTool())
