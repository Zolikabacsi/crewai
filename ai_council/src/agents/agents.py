"""Agent definitions for AI Council crew."""

import os
from crewai import Agent
from crewai.llm import LLM
from crewai_tools import DirectoryReadTool, FileReadTool
from ..config import Config

if Config.ANTHROPIC_AUTH_TOKEN and Config.ANTHROPIC_BASE_URL:
    os.environ["ANTHROPIC_API_KEY"] = Config.ANTHROPIC_AUTH_TOKEN
    os.environ["ANTHROPIC_BASE_URL"] = Config.ANTHROPIC_BASE_URL


def get_llm():
    return LLM(
        provider="anthropic",
        model="MiniMax-M2.7",
        api_key=Config.ANTHROPIC_AUTH_TOKEN,
        base_url=Config.ANTHROPIC_BASE_URL,
    )


def load_prompt(filename: str) -> str:
    """Load a partner prompt from file."""
    path = Config.PROMPTS_DIR / filename
    if path.exists():
        with open(path, 'r') as f:
            return f.read()
    return ""


class CEOPartner(Agent):
    def __init__(self):
        prompt = load_prompt("CEO_PARTNER_PROMPT.md")
        super().__init__(
            role="CEO Partner",
            goal="Strategic executive-level guidance",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class CFOPartner(Agent):
    def __init__(self):
        prompt = load_prompt("CFO_PARTNER_-_Strategic_Financial_Thinking.md")
        super().__init__(
            role="CFO Partner",
            goal="Strategic financial guidance",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class CMOPartner(Agent):
    def __init__(self):
        prompt = load_prompt("CMO_PARTNER_PROMPT_STRATEGIC_THINKING.md")
        super().__init__(
            role="CMO Partner",
            goal="Strategic marketing guidance",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class CTOPartner(Agent):
    def __init__(self):
        prompt = load_prompt("CTO_PARTNER_Strategic_Technology_Decision.md")
        super().__init__(
            role="CTO Partner",
            goal="Strategic technology decisions",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class COOPartner(Agent):
    def __init__(self):
        prompt = load_prompt("COO_PARTNER_PROMPT_OPERATIONAL.md")
        super().__init__(
            role="COO Partner",
            goal="Operational excellence guidance",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class CoFounderPartner(Agent):
    def __init__(self):
        prompt = load_prompt("CO-FOUNDER_PARTNER_PROMPT.md")
        super().__init__(
            role="Co-Founder Partner",
            goal="Strategic sparring and execution",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class CoachPartner(Agent):
    def __init__(self):
        prompt = load_prompt("COACH_PARTNER_PROMPT.md")
        super().__init__(
            role="Coach Partner",
            goal="Founder mindset and performance",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class IntelligencePartner(Agent):
    def __init__(self):
        prompt = load_prompt("Intelligence_Partner_Agent_Prompt.md")
        super().__init__(
            role="Intelligence Partner",
            goal="Market and competitive intelligence",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class DevilsAdvocatePartner(Agent):
    def __init__(self):
        prompt = load_prompt("DEVILS_ADVOCATE_PARTNER_PROMPT.md")
        super().__init__(
            role="Devil's Advocate Partner",
            goal="Stress test and identify weaknesses",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class AdvisorPartner(Agent):
    def __init__(self):
        prompt = load_prompt("ADVISOR_PARTNER_PROMPT.md")
        super().__init__(
            role="Advisor Partner",
            goal="Structured thinking and pattern matching",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class InvestorPartner(Agent):
    def __init__(self):
        prompt = load_prompt("INVESTOR_PARTNER_AGENT.md")
        super().__init__(
            role="Investor Partner",
            goal="Investor perspective and funding guidance",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class BoardMemberPartner(Agent):
    def __init__(self):
        prompt = load_prompt("BOARD_MEMBER_PARTNER_PROMPT.md")
        super().__init__(
            role="Board Member Partner",
            goal="Governance and long-term value",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class ContentStrategyPartner(Agent):
    def __init__(self):
        prompt = load_prompt("CONTENT_STRATEGY_PARTNER_PROMPT.md")
        super().__init__(
            role="Content Strategy Partner",
            goal="Content strategy and execution guidance",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class CustomerPartner(Agent):
    def __init__(self):
        prompt = load_prompt("CUSTOMER_PARTNER_STRATEGIC_THINKING.md")
        super().__init__(
            role="Customer Partner",
            goal="Customer perspective and validation",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class DemandGenPartner(Agent):
    def __init__(self):
        prompt = load_prompt("DEMAND_GEN_STRATEGY_PARTNER_PROMPT.md")
        super().__init__(
            role="Demand Generation Partner",
            goal="Demand generation and growth strategy",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class FirstPrinciplesPartner(Agent):
    def __init__(self):
        prompt = load_prompt("FIRST_PRINCIPLES_PARTNER_Strategic_Prompt.md")
        super().__init__(
            role="First Principles Partner",
            goal="First-principles reasoning and root cause analysis",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class HeadOfProductPartner(Agent):
    def __init__(self):
        prompt = load_prompt("HEAD_OF_PRODUCT_PARTNER_PROMPT.md")
        super().__init__(
            role="Head of Product Partner",
            goal="Product strategy and roadmap guidance",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class StartupGTMPartner(Agent):
    def __init__(self):
        prompt = load_prompt("StartupGTM_AI_Partners_Council_System.md")
        super().__init__(
            role="Startup GTM Partner",
            goal="Go-to-market strategy and launch planning",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


def get_council_agents():
    return [
        CEOPartner(),
        CFOPartner(),
        CMOPartner(),
        CTOPartner(),
        COOPartner(),
        CoFounderPartner(),
        CoachPartner(),
        IntelligencePartner(),
        DevilsAdvocatePartner(),
        AdvisorPartner(),
        InvestorPartner(),
        BoardMemberPartner(),
        ContentStrategyPartner(),
        CustomerPartner(),
        DemandGenPartner(),
        FirstPrinciplesPartner(),
        HeadOfProductPartner(),
        StartupGTMPartner(),
    ]


def get_core_agents():
    """Essential agents for a quick board meeting."""
    return [
        CoFounderPartner(),
        CoachPartner(),
        IntelligencePartner(),
        DevilsAdvocatePartner(),
    ]