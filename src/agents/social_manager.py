"""Social Media Manager Agent — Content Calendar & Platform Management.

This sub-agent works under the CMO for the Aestas Healthcare project.
It creates content calendars, writes posts, manages publishing schedules,
and tracks engagement across platforms.
"""

from crewai import Agent
from crewai.llm import LLM
from crewai_tools import DirectoryReadTool, FileReadTool, TavilySearchTool
from ..config import Config
from ..agent_storage import VaultStorageTool
from ..tools import AgentBusTool
from pathlib import Path

import os

# Ensure environment is configured for custom endpoints
if Config.ANTHROPIC_AUTH_TOKEN:
    os.environ["ANTHROPIC_API_KEY"] = Config.ANTHROPIC_AUTH_TOKEN
if Config.ANTHROPIC_BASE_URL:
    os.environ["ANTHROPIC_BASE_URL"] = Config.ANTHROPIC_BASE_URL.rstrip("/v1")

# Vault path for Aestas CMO sub-agent outputs
VAULT_CMO_PATH = Path("/home/zoltan/srv/vault/Second Brain/raw/Aestas_CMO")


def get_llm():
    """Create LLM instance for Social Media Manager agent with MiniMax-M2.7 model."""
    return LLM(
        provider="anthropic",
        model="MiniMax-M2.7",
        api_key=Config.ANTHROPIC_AUTH_TOKEN,
        base_url=Config.ANTHROPIC_BASE_URL.rstrip("/v1") if Config.ANTHROPIC_BASE_URL else "https://chat.ultimateai.org",
    )


class SocialMediaManager(Agent):
    """Social media manager with multi-platform expertise.

    This agent has deep knowledge of:
    - LinkedIn, Facebook, Twitter/X content strategies
    - Platform algorithms and engagement optimization
    - Content repurposing across networks
    - Healthcare social media compliance
    - Hungarian and European social media patterns

    Works under the CMO to execute the social media strategy
    for Aestas Healthcare brand presence.
    """

    def __init__(self):
        from ..marketing.skill_loader import SkillLoaderTool
        from ai_council.src.agents.zernio_tools import ZernioPostTool
        super().__init__(
            role="Social Media Manager",
            goal=(
                "You are a social media manager. You create content calendars, write posts, "
                "manage publishing schedules, and track engagement across platforms. "
                "You work with the CMO to execute the social media strategy for Aestas Healthcare, "
                "ensuring consistent brand presence and high engagement on LinkedIn and other platforms."
            ),
            backstory=(
                "You are a social media expert with deep knowledge of LinkedIn, platform algorithms, "
                "engagement strategies, and content repurposing across multiple social networks. "
                "You have built audiences for healthcare and medical brands, understanding the "
                "balance between engaging content and regulatory compliance. You know how to "
                "craft posts that drive meaningful engagement rather than vanity metrics. "
                "You speak Hungarian and understand the Central European social media landscape."
            ),
            verbose=Config.VERBOSE,
            tools=[
                DirectoryReadTool(),
                FileReadTool(),
                TavilySearchTool(),
                SkillLoaderTool(),
                VaultStorageTool(agent_folder="Aestas_CMO", sub_folder="social_posts"),
                AgentBusTool(),
                ZernioPostTool(),
            ],
            llm=get_llm(),
        )


def get_social_manager() -> SocialMediaManager:
    """Factory function to create the Social Media Manager agent."""
    return SocialMediaManager()
