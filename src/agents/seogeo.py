"""SEO/GEO Specialist Agent — Search Engine & Generative Engine Optimization.

This sub-agent works under the CMO for the Aestas Healthcare project.
It researches keywords, analyzes competitors, and creates optimization briefs
for both traditional search engines and AI-powered search platforms.
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
    """Create LLM instance for SEO/GEO Specialist agent with MiniMax-M2.7 model."""
    return LLM(
        provider="anthropic",
        model="MiniMax-M2.7",
        api_key=Config.ANTHROPIC_AUTH_TOKEN,
        base_url=Config.ANTHROPIC_BASE_URL.rstrip("/v1") if Config.ANTHROPIC_BASE_URL else "https://chat.ultimateai.org",
    )


class SEOGEOSpecialist(Agent):
    """SEO and GEO (Generative Engine Optimization) specialist.

    This agent has deep expertise in:
    - Keyword research and competitive analysis
    - Traditional SEO optimization (technical, on-page, off-page)
    - GEO optimization for AI search platforms (Perplexity, ChatGPT, etc.)
    - Healthcare content optimization
    - Hungarian and European search market patterns

    Works under the CMO to create optimization briefs and guidance
    for Aestas Healthcare content marketing.
    """

    def __init__(self):
        from ..marketing.skill_loader import SkillLoaderTool
        super().__init__(
            role="SEO/GEO Specialist",
            goal=(
                "You are an SEO and GEO (Generative Engine Optimization) specialist. "
                "You help the CMO optimize content for search engines and AI search platforms. "
                "You research keywords, analyze competitors, and create optimization briefs "
                "that improve organic visibility and AI reference rates for Aestas Healthcare content."
            ),
            backstory=(
                "You are a data-driven SEO/GEO expert with deep knowledge of search algorithms, "
                "keyword research, and content optimization for both traditional search engines "
                "and AI-powered search platforms like Perplexity and ChatGPT. You understand "
                "how AI models ingest and reference web content, allowing you to optimize for "
                "both human readers and AI systems. You have worked extensively in healthcare "
                "and medical content, understanding the unique compliance and accuracy requirements. "
                "You speak Hungarian and understand Central European search behavior."
            ),
            verbose=Config.VERBOSE,
            tools=[
                DirectoryReadTool(),
                FileReadTool(),
                TavilySearchTool(),
                SkillLoaderTool(),
                VaultStorageTool(agent_folder="Aestas_CMO", sub_folder="seo_briefs"),
                AgentBusTool(),
            ],
            llm=get_llm(),
        )


def get_seogeo() -> SEOGEOSpecialist:
    """Factory function to create the SEO/GEO Specialist agent."""
    return SEOGEOSpecialist()
