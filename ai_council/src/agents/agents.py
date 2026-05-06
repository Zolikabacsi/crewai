"""Agent definitions for AI Council crew."""

import os
import sys
from pathlib import Path

# Allow imports from src/ (sibling package at project root)
# agents.py is at ai_council/src/agents/ → 4 levels up = project root ~/srv/crewai/
_CREWAI_ROOT = str(Path(__file__).parent.parent.parent.parent)
if _CREWAI_ROOT not in sys.path:
    sys.path.insert(0, _CREWAI_ROOT)

from crewai import Agent
from crewai.llm import LLM
from crewai_tools import DirectoryReadTool, FileReadTool, TavilySearchTool
from ai_council.src.config import Config
from src.agent_storage import VaultStorageTool
from src.tools import VaultSearchTool, VaultReadTool, AgentBusTool
from src.marketing.skill_loader import SkillLoaderTool
from .zernio_tools import ZernioPostTool, ZernioListAccountsTool, ZernioListPostsTool

if Config.ANTHROPIC_AUTH_TOKEN and Config.ANTHROPIC_BASE_URL:
    os.environ["ANTHROPIC_API_KEY"] = Config.ANTHROPIC_AUTH_TOKEN
    os.environ["ANTHROPIC_BASE_URL"] = Config.ANTHROPIC_BASE_URL.rstrip("/v1")


def get_llm():
    return LLM(
        provider="anthropic",
        model="MiniMax-M2.7",
        api_key=Config.ANTHROPIC_AUTH_TOKEN,
        base_url=Config.ANTHROPIC_BASE_URL.rstrip("/v1") if Config.ANTHROPIC_BASE_URL else None,
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
        # Append operational mode delegation section to the board-mode strategic thinking
        operational_mode = (
            "\n\n== OPERATIONAL MODE — SUB-AGENT DELEGATION ==\n"
            "When given a financial analysis, pricing, or ROI task:\n"
            "  1. SEARCH PRIOR CONTEXT: At the start of each task, use memory search to find "
            "relevant prior analyses, decisions, or context from previous sessions.\n"
            "  2. CLASSIFY the task type:\n"
            "     - Unit economics / margin / revenue model → FinancialAnalysisAgent\n"
            "     - Pricing options / subscription / freemium → PricingStrategyAgent\n"
            "     - ROI / payback period / LTV/CAC → ROIAnalysisAgent\n"
            "  3. DELEGATE to the appropriate specialist sub-agent:\n"
            "     - FinancialAnalysisAgent → P&L analysis, SaaS metrics, margin profiles, revenue viability\n"
            "     - PricingStrategyAgent → Pricing psychology, value-based pricing, model comparison\n"
            "     - ROIAnalysisAgent → Investment ROI, payback period, LTV/CAC ratio analysis\n"
            "  4. COLLECT outputs from sub-agents\n"
            "  5. SYNTHESIZE into the final financial recommendation\n"
            "  6. SAVE KEY INSIGHTS: After completing each task, save important findings, "
            "decisions, and context to memory for future sessions.\n\n"
            "CFO tools available: financial modeling, pricing analysis, investment evaluation, "
            "vault storage for permanent document archival.\n"
            "Keep the full board-mode 7-step strategic financial thinking framework intact as the foundation."
        )
        full_backstory = prompt + operational_mode

        super().__init__(
            role="CFO Partner",
            goal=(
                "Serve as CFO with voting rights on the board. "
                "BOARD MODE: strategic financial diagnosis using the 7-step framework; "
                "OPERATIONAL MODE: delegate to specialist sub-agents (FinancialAnalysisAgent, "
                "PricingStrategyAgent, ROIAnalysisAgent) for detailed financial analysis."
            ),
            backstory=full_backstory,
            verbose=Config.VERBOSE,
            tools=[
                DirectoryReadTool(),
                FileReadTool(),
                TavilySearchTool(),
                VaultSearchTool(),
                VaultReadTool(),
                VaultStorageTool(agent_folder="Aestas_CFO", sub_folder="analyses"),
                AgentBusTool(),
            ],
            llm=get_llm(),
        )


class CMOPartner(Agent):
    def __init__(self):
        prompt = load_prompt("CMO_PARTNER_PROMPT_STRATEGIC_THINKING.md")
        # Append operational mode delegation section to the board-mode strategic thinking
        operational_mode = (
            "\n\n== OPERATIONAL MODE — SUB-AGENT DELEGATION ==\n"
            "When given a marketing task (post, copy, campaign, SEO brief, etc.):\n"
            "  1. LOAD the relevant marketingskill first using SkillLoaderTool:\n"
            "     - SEO/keywords → ai-seo + content-strategy\n"
            "     - Social posts → social-content + copywriting\n"
            "     - Landing/copy pages → copywriting + page-cro\n"
            "     - Email sequences → cold-email + email-sequence\n"
            "     - Competitor analysis → competitor-profiling\n"
            "     - Analytics/tracking → analytics-tracking\n"
            "  2. DELEGATE to the right sub-agent:\n"
            "     - SEOGEOSpecialist → keyword research, content briefs, optimization\n"
            "     - SocialMediaManager → content calendars, post writing, platform strategy\n"
            "     - Copywriter → all written content, drafts, editing\n"
            "  3. COLLECT outputs from sub-agents\n"
            "  4. SYNTHESIZE into the final deliverable\n\n"
            "Keep the full board-mode 6-step strategic thinking framework intact as the foundation."
        )
        full_backstory = prompt + operational_mode
        
        super().__init__(
            role="CMO Partner",
            goal=(
                "Serve as CMO with full voting rights on the Aestas Healthcare board. "
                "Two modes: (1) BOARD MODE — evaluate business ideas through structured strategic diagnosis; "
                "(2) OPERATIONAL MODE — lead marketing execution by delegating to specialist sub-agents "
                "(SEOGEOSpecialist, SocialMediaManager, Copywriter) using marketingskills, "
                "synthesize their outputs, and deliver final campaigns."
            ),
            backstory=full_backstory,
            verbose=Config.VERBOSE,
            tools=[
                DirectoryReadTool(),
                FileReadTool(),
                TavilySearchTool(),
                SkillLoaderTool(),
                ZernioPostTool(),
                ZernioListAccountsTool(),
                ZernioListPostsTool(),
                VaultStorageTool(agent_folder="Aestas_CMO", sub_folder="campaigns"),
                AgentBusTool(),
            ],
            llm=get_llm(),
        )


class CMedOPartner(Agent):
    def __init__(self):
        prompt = load_prompt("CMEDO_PARTNER_PROMPT.md")
        super().__init__(
            role="CMedO Partner",
            goal="Medical, clinical, patient safety, privacy, GDPR/HIPAA, and regulatory thought partner with VETO RIGHTS",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool(), TavilySearchTool(), VaultStorageTool()],
            llm=get_llm(),
        )


class CTOPartner(Agent):
    def __init__(self):
        prompt = load_prompt("CTO_PARTNER_Strategic_Technology_Decision.md")
        # Append operational mode delegation section to the board-mode strategic thinking
        operational_mode = (
            "\n\n== OPERATIONAL MODE — SUB-AGENT DELEGATION ==\n"
            "When given a technology evaluation, build vs. buy, or architecture task:\n"
            "  1. CLASSIFY the task type:\n"
            "     - Tech stack / tool evaluation → TechStackEvaluator\n"
            "     - Build vs. buy vs. integrate → BuildVsBuyAgent\n"
            "     - Architecture / scalability / security → ArchitectureReviewAgent\n"
            "  2. DELEGATE to the appropriate specialist sub-agent:\n"
            "     - TechStackEvaluator → Stack maturity, maintenance burden, tooling decisions\n"
            "     - BuildVsBuyAgent → Build vs. buy vs. integrate decision frameworks\n"
            "     - ArchitectureReviewAgent → System architecture, scalability, cost review\n"
            "  3. COLLECT outputs from sub-agents\n"
            "  4. SYNTHESIZE into the final technology recommendation\n"
            "  5. SAVE KEY INSIGHTS: After completing each task, save important findings,\n"
            "decisions, and technical context to memory for future sessions.\n\n"
            "CTO tools available: tech stack evaluation, build vs. buy analysis, architecture review,\n"
            "vault storage for permanent document archival.\n"
            "Keep the full board-mode 6-phase strategic technology decision framework intact as the foundation."
        )
        full_backstory = prompt + operational_mode

        super().__init__(
            role="CTO Partner",
            goal=(
                "Serve as CTO with voting rights on the board. "
                "BOARD MODE: strategic technology diagnosis using the 6-phase framework; "
                "OPERATIONAL MODE: delegate to specialist sub-agents (TechStackEvaluator, "
                "BuildVsBuyAgent, ArchitectureReviewAgent) for detailed technology analysis."
            ),
            backstory=full_backstory,
            verbose=Config.VERBOSE,
            tools=[
                DirectoryReadTool(),
                FileReadTool(),
                TavilySearchTool(),
                VaultStorageTool(agent_folder="Aestas_CTO", sub_folder="tech_decisions"),
                AgentBusTool(),
            ],
            llm=get_llm(),
        )


class COOPartner(Agent):
    def __init__(self):
        prompt = load_prompt("COO_PARTNER_PROMPT_OPERATIONAL.md")
        # Append operational mode delegation section to the board-mode operational thinking
        operational_mode = (
            "\n\n== OPERATIONAL MODE — SUB-AGENT DELEGATION ==\n"
            "When given an operations, process, capacity, or organizational design task:\n"
            "  1. CLASSIFY the task type:\n"
            "     - Workflow / process design → ProcessDesigner\n"
            "     - Team capacity / hiring / workload → CapacityPlanner\n"
            "     - Decision rights / accountability → RACIMapper\n"
            "  2. DELEGATE to the appropriate specialist sub-agent:\n"
            "     - ProcessDesigner → Operational workflow design, documentation, automation\n"
            "     - CapacityPlanner → Team sizing, hiring plans, workload distribution\n"
            "     - RACIMapper → Decision rights, accountability, RACI matrix development\n"
            "  3. COLLECT outputs from sub-agents\n"
            "  4. SYNTHESIZE into the final operational recommendation\n"
            "  5. SAVE KEY INSIGHTS: After completing each task, save important findings,\n"
            "decisions, and operational context to memory for future sessions.\n\n"
            "COO tools available: process design, capacity planning, organizational design,\n"
            "vault storage for permanent document archival.\n"
            "Keep the full board-mode 6-stage operational thinking framework intact as the foundation."
        )
        full_backstory = prompt + operational_mode

        super().__init__(
            role="COO Partner",
            goal=(
                "Serve as COO with voting rights on the board. "
                "BOARD MODE: operational diagnosis using the 6-stage framework; "
                "OPERATIONAL MODE: delegate to specialist sub-agents (ProcessDesigner, "
                "CapacityPlanner, RACIMapper) for detailed operational analysis."
            ),
            backstory=full_backstory,
            verbose=Config.VERBOSE,
            tools=[
                DirectoryReadTool(),
                FileReadTool(),
                TavilySearchTool(),
                VaultStorageTool(agent_folder="Aestas_COO", sub_folder="operational_docs"),
                AgentBusTool(),
            ],
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


class BrandManagerPartner(Agent):
    def __init__(self):
        prompt = load_prompt("BRAND_MANAGER_PARTNER_PROMPT.md")
        super().__init__(
            role="Brand Manager",
            goal="Brand stewardship, voice consistency, and brand asset development for Aestas Healthcare",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[
                DirectoryReadTool(),
                FileReadTool(),
                TavilySearchTool(),
                VaultStorageTool(),
                AgentBusTool(),
            ],
            llm=get_llm(),
        )


class ResearcherPartner(Agent):
    def __init__(self):
        prompt = load_prompt("RESEARCHER_PARTNER_PROMPT.md")
        super().__init__(
            role="Research Partner",
            goal="Deep research, market intelligence, and competitive analysis",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool(), TavilySearchTool(), VaultStorageTool()],
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
        ResearcherPartner(),
        BrandManagerPartner(),
    ]


def get_core_agents():
    """Essential agents for a quick board meeting."""
    return [
        CoFounderPartner(),
        CoachPartner(),
        IntelligencePartner(),
        DevilsAdvocatePartner(),
    ]