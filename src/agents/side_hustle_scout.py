"""Side Hustle Scout agent — monitors web sources, consults council, routes to Slack."""

from crewai import Agent
from crewai.llm import LLM
from ..config import Config
from ..tools import WebScraperTool, IndustryReportTool, OpportunityStorageTool

_AUTH = Config.ANTHROPIC_AUTH_TOKEN
_BASE = Config.ANTHROPIC_BASE_URL

if _AUTH and _BASE:
    import os
    os.environ["ANTHROPIC_API_KEY"] = _AUTH
    os.environ["ANTHROPIC_BASE_URL"] = _BASE


def get_llm():
    return LLM(
        provider="anthropic",
        model="MiniMax-M2.7",
        api_key=Config.ANTHROPIC_AUTH_TOKEN,
        base_url=Config.ANTHROPIC_BASE_URL,
    )


class SideHustleScout(Agent):
    def __init__(self):
        super().__init__(
            role="Side Hustle Opportunity Scout",
            goal=(
                "Continuously identify, evaluate, and surface viable side income opportunities "
                "that match the user's profile and capabilities. Always consult Coach and "
                "Devil's Advocate before surfacing any opportunity. Route extraordinary finds "
                "to immediate Slack alerts; include regular finds in daily digest."
            ),
            backstory=(
                "You are a relentless business development analyst who monitors freelance markets, "
                "startup communities, and industry trends to surface side hustle opportunities. "
                "You evaluate each opportunity rigorously, consult the right experts before surfacing "
                "anything, and only escalate truly extraordinary finds. You are based in Europe "
                "and understand both EU and non-EU market dynamics."
            ),
            verbose=Config.VERBOSE,
            tools=[
                WebScraperTool(),
                IndustryReportTool(),
                OpportunityStorageTool(),
            ],
            llm=get_llm(),
        )