"""Agent definitions for the business idea evaluator crew.

Each agent is specialized for a specific aspect of business evaluation:
- MarketResearcher: Analyzes market size, trends, and competition
- FinancialAnalyst: Evaluates financial viability, costs, and projections
- RiskAssessor: Identifies and evaluates potential risks
- BusinessWriter: Synthesizes findings into a comprehensive report
"""

from crewai import Agent
from crewai.llm import LLM
from crewai_tools import DirectoryReadTool, FileReadTool
from ..config import Config

import os

# Ensure environment is configured for custom endpoints
if Config.ANTHROPIC_AUTH_TOKEN:
    os.environ["ANTHROPIC_API_KEY"] = Config.ANTHROPIC_AUTH_TOKEN
if Config.ANTHROPIC_BASE_URL:
    os.environ["ANTHROPIC_BASE_URL"] = Config.ANTHROPIC_BASE_URL.rstrip("/v1")


def get_llm():
    """Create LLM instance for agents with MiniMax-M2.7 model via Anthropic endpoint."""
    return LLM(
        provider="anthropic",
        model="MiniMax-M2.7",
        api_key=Config.ANTHROPIC_AUTH_TOKEN,
        base_url=Config.ANTHROPIC_BASE_URL.rstrip("/v1") if Config.ANTHROPIC_BASE_URL else "https://chat.ultimateai.org",
    )


class MarketResearcher(Agent):
    """Agent specialized in market research and competitive analysis."""

    def __init__(self):
        super().__init__(
            role="Market Research Analyst",
            goal="Provide data-driven insights on market size, trends, and competition",
            backstory=(
                "You are an experienced market analyst with 15+ years of experience "
                "evaluating business opportunities across various industries. You have "
                "a knack for identifying market gaps and emerging trends. Your insights "
                "help businesses understand their competitive landscape and market potential."
            ),
            verbose=Config.VERBOSE,
            tools=[
                DirectoryReadTool(),
                FileReadTool(),
            ],
            llm=get_llm(),
        )


class FinancialAnalyst(Agent):
    """Agent specialized in financial analysis and projections."""

    def __init__(self):
        super().__init__(
            role="Financial Analyst",
            goal="Evaluate the financial viability and growth potential of business ideas",
            backstory=(
                "You are a seasoned financial analyst with expertise in startup valuation, "
                "revenue modeling, and investment analysis. You've helped secure over $50M "
                "in funding by providing rigorous financial assessments. You excel at "
                "identifying cost structures and revenue opportunities."
            ),
            verbose=Config.VERBOSE,
            tools=[
                DirectoryReadTool(),
                FileReadTool(),
            ],
            llm=get_llm(),
        )


class RiskAssessor(Agent):
    """Agent specialized in identifying and evaluating business risks."""

    def __init__(self):
        super().__init__(
            role="Risk Assessment Specialist",
            goal="Identify, analyze, and mitigate potential risks in business ventures",
            backstory=(
                "You are a risk management expert who has consulted for Fortune 500 companies "
                "and early-stage startups alike. Your systematic approach to risk identification "
                "has helped numerous ventures avoid costly mistakes. You think holistically "
                "about operational, market, financial, and regulatory risks."
            ),
            verbose=Config.VERBOSE,
            tools=[
                DirectoryReadTool(),
                FileReadTool(),
            ],
            llm=get_llm(),
        )


class BusinessWriter(Agent):
    """Agent specialized in synthesizing analyses into comprehensive reports."""

    def __init__(self):
        super().__init__(
            role="Business Report Writer",
            goal="Synthesize all analyses into a clear, actionable business evaluation report",
            backstory=(
                "You are a professional business writer who has authored hundreds of successful "
                "business plans, pitch decks, and market analysis reports. Your writing helps "
                "stakeholders quickly understand complex business concepts and make informed "
                "decisions. You have a talent for distilling technical analysis into actionable insights."
            ),
            verbose=Config.VERBOSE,
            tools=[
                DirectoryReadTool(),
                FileReadTool(),
            ],
            llm=get_llm(),
        )


def get_all_agents():
    """Factory function to create all agents for the crew."""
    return [
        MarketResearcher(),
        FinancialAnalyst(),
        RiskAssessor(),
        BusinessWriter(),
    ]