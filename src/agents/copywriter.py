"""Copywriter Agent — Professional Medical & Marketing Copy.

This sub-agent works under the CMO for the Aestas Healthcare project.
It writes compelling, clear, accurate medical copy for patient education,
marketing materials, social posts, and web content.
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
    """Create LLM instance for Copywriter agent with MiniMax-M2.7 model."""
    return LLM(
        provider="anthropic",
        model="MiniMax-M2.7",
        api_key=Config.ANTHROPIC_AUTH_TOKEN,
        base_url=Config.ANTHROPIC_BASE_URL.rstrip("/v1") if Config.ANTHROPIC_BASE_URL else "https://chat.ultimateai.org",
    )


class Copywriter(Agent):
    """Professional healthcare copywriter.

    This agent has expertise in:
    - Patient education materials (Hungarian language)
    - Marketing copy for healthcare brands
    - Social media posts and captions
    - Web content and landing pages
    - Medical accuracy and regulatory compliance
    - Ethical healthcare marketing standards

    Works under the CMO to produce all written content
    for Aestas Healthcare marketing initiatives.
    """

    def __init__(self):
        from ..marketing.skill_loader import SkillLoaderTool
        super().__init__(
            role="Copywriter",
            goal=(
                "You are a professional copywriter. You write compelling, clear, accurate medical copy "
                "for patient education, marketing materials, social posts, and web content. "
                "Hungarian language a plus. You work with the CMO to produce all written content "
                "for Aestas Healthcare, maintaining high ethical standards and regulatory compliance."
            ),
            backstory=(
                "You are a healthcare copywriter with a talent for translating complex medical information "
                "into accessible, engaging content. You understand regulatory constraints in medical "
                "marketing and maintain high ethical standards — no misleading claims, no overpromising. "
                "You have written for dermatology, aesthetics, and preventive healthcare brands, "
                "understanding both the clinical nuances and patient concerns. You speak Hungarian "
                "natively and can write in both Hungarian and English at a professional level. "
                "You know that the best healthcare copy educates first and promotes second."
            ),
            verbose=Config.VERBOSE,
            tools=[
                DirectoryReadTool(),
                FileReadTool(),
                TavilySearchTool(),
                SkillLoaderTool(),
                VaultStorageTool(agent_folder="Aestas_CMO", sub_folder="copy"),
                AgentBusTool(),
            ],
            llm=get_llm(),
        )


def get_copywriter() -> Copywriter:
    """Factory function to create the Copywriter agent."""
    return Copywriter()
