"""CFO Operational Agent — run_cfo_task entry point + sub-agent task prompts.

run_cfo_task() is the daemon entry point. It classifies the incoming question
into one of three sub-agent domains (FinancialAnalysis, PricingStrategy, ROIAnalysis),
calls Claude Code with the appropriate sub-agent prompt, synthesizes the result,
and saves to vault.

Vault: /home/zoltan/srv/vault/Second Brain/raw/Aestas_CFO/
"""

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ── Paths ────────────────────────────────────────────────────────────────────
_CREWAI_ROOT = Path(__file__).parent.parent.parent
_SRC_DIR = _CREWAI_ROOT / "src"
_PROMPTS_DIR = _CREWAI_ROOT / "ai_council" / "prompts"
sys.path.insert(0, str(_CREWAI_ROOT))
sys.path.insert(0, str(_SRC_DIR))

from src.config import Config
from src.agent_storage import VaultStorageTool
from src.tools.second_brain_tool import SecondBrainKnowledgeTool

VAULT_ROOT = Path("/home/zoltan/srv/vault/Second Brain/raw/Aestas_CFO")
CLAUDE_BIN = Path("/home/zoltan/.local/bin/claude")

# ── Vault context helper ──────────────────────────────────────────────────────
_vault_tool = SecondBrainKnowledgeTool()


def _get_vault_context(question: str, sections: list[str] | None = None) -> str:
    """Fetch relevant vault context before calling sub-agents."""
    try:
        ctx = _vault_tool._run(query=question, sections=sections)
        if ctx and "not found" not in ctx.lower()[:100] and "No results" not in ctx:
            return f"\n\n## Relevant Context from Second Brain Vault\n{ctx}\n"
    except Exception:
        pass
    return ""


# ── Sub-agent prompt templates ────────────────────────────────────────────────
# These are invoked via Claude Code subprocess (same pattern as CMedO/Researcher)

_SUB_AGENT_PROMPTS = {
    "financial_analysis": """You are FinancialAnalysisAgent — a rigorous financial analyst specializing in unit economics, P&L analysis, and SaaS metrics.

Aestas Healthcare context (known):
- Revenue model: subscription telemedicine (B2C + B2B)
- Current stage: early growth
- Presence: Cyprus (HE391166), Sweden (180 days max/year), Hungary (ER + private)

Task: {question}

Provide a structured financial analysis covering:
1. Key financial assumptions stated
2. Revenue model assessment (unit economics, margins)
3. P&L structure (if applicable)
4. SaaS metrics (MRR, ARR, churn, LTV, CAC where applicable)
5. Key risks and red flags
6. Recommended next steps

Be specific. State assumptions clearly. Flag uncertainty.""",

    "pricing_strategy": """You are PricingStrategyAgent — a pricing strategist who understands price as a strategic signal.

Aestas Healthcare context (known):
- Revenue model: subscription telemedicine (B2C + B2B)
- Markets: Cyprus, Sweden, Hungary (cross-border)
- Stage: early growth

Task: {question}

Provide a structured pricing strategy analysis covering:
1. Current pricing context (if known)
2. Pricing options evaluated (subscription, per-session, freemium, hybrid)
3. Value-based pricing rationale
4. Price elasticity considerations
5. Competitive positioning implications
6. Recommended pricing model with rationale
7. Risk factors

Be specific about pricing tiers, psychological anchoring, and competitive signals.""",

    "roi_analysis": """You are ROIAnalysisAgent — quantifies ROI, payback periods, and long-term value.

Aestas Healthcare context (known):
- Revenue model: subscription telemedicine (B2C + B2B)
- Presence: Cyprus, Sweden, Hungary
- Stage: early growth

Task: {question}

Provide a structured ROI analysis covering:
1. Investment/opportunity described
2. Assumptions stated explicitly
3. Payback period calculation
4. ROI / IRR / NPV where applicable
5. LTV/CAC ratio implications
6. Scenario analysis (best/base/worst case)
7. Recommendation with key risks
8. Sensitivity analysis on critical assumptions

Show your work. Every number traces back to an assumption.""",
}

# Keyword-based task classifier
_TASK_KEYWORDS = {
    "financial_analysis": [
        "margin", "profit", "revenue", "burn rate", "runway", "cash flow",
        "unit economics", "coa", "coe", " Arl", "ARR", "MRR", "churn",
        "ltv", "cac", "p&l", "income statement", "balance sheet", "financial",
        "break-even", "breakeven", "cost structure", "opex", "capex",
    ],
    "pricing_strategy": [
        "pricing", "price", "subscription", "freemium", "tier", "packag",
        "value-based", "willingness to pay", "price increase", "discount",
        "license", "transactional", "per session", "per-visit",
    ],
    "roi_analysis": [
        "roi", "return on investment", "payback", "npv", "irr", "roi",
        "ltv/cac", "investment", "capital", "budget", "cost benefit",
        "lifetime value", "acquisition cost",
    ],
}


def _classify_question(question: str) -> str:
    """Classify a question into a sub-agent domain by keyword scoring."""
    q_lower = question.lower()
    scores = {}
    for domain, keywords in _TASK_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in q_lower)
        scores[domain] = score

    # Return highest scoring domain, default to financial_analysis
    if max(scores.values()) > 0:
        return max(scores, key=scores.get)
    return "financial_analysis"


def _call_sub_agent(domain: str, question: str) -> str:
    """Call Claude Code subprocess with the appropriate sub-agent prompt.

    Uses --output-format json so we can reliably extract the text response.
    Pre-fetches vault context for CFO section to ground the analysis.
    Returns the raw text response (stripped of markdown fences).
    """
    prompt_template = _SUB_AGENT_PROMPTS.get(domain, _SUB_AGENT_PROMPTS["financial_analysis"])

    # Pre-fetch relevant vault context
    vault_ctx = _get_vault_context(question, sections=["CFO"])

    prompt = prompt_template.format(question=question) + vault_ctx

    # Build environment
    env = {
        "HOME": os.environ.get("HOME", "/home/zoltan"),
        "ANTHROPIC_API_KEY": Config.ANTHROPIC_AUTH_TOKEN or "",
        "ANTHROPIC_BASE_URL": Config.ANTHROPIC_BASE_URL or "https://chat.ultimateai.org",
    }

    try:
        result = subprocess.run(
            [
                str(CLAUDE_BIN),
                "-p",
                prompt,  # positional arg (not stdin)
                "--model", "MiniMax-M2.7",
                "--output-format", "json",
                "--bare",  # non-interactive mode (no TTY required)
            ],
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )

        # Unwrap Claude Code JSON response
        raw = result.stdout.strip()
        try:
            parsed = json.loads(raw)
            text = parsed.get("result", parsed.get("content", ""))
        except json.JSONDecodeError:
            # Try stripping markdown fences
            text = re.sub(r"^```json\s*", "", raw, flags=re.IGNORECASE)
            text = re.sub(r"^```\s*", "", text)
            text = text.strip().strip("`")
            try:
                inner = json.loads(text)
                text = inner.get("result", inner.get("content", text))
            except json.JSONDecodeError:
                text = text  # use as-is

        return text

    except subprocess.TimeoutExpired:
        return f"[TIMEOUT] Claude Code timed out after 300s for domain: {domain}"
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}"


def _synthesize_analysis(domain: str, sub_agent_result: str, question: str) -> str:
    """Synthesize the sub-agent result into a final CFO analysis."""
    synthesis_prompt = f"""Synthesize the following CFO sub-agent analysis into a final structured output.

ORIGINAL QUESTION: {question}
SUB-AGENT DOMAIN: {domain}

SUB-AGENT ANALYSIS:
{sub_agent_result}

Produce a final CFO analysis in this format:
## CFO Analysis: [brief title from question]

### Context & Assumptions
(list key assumptions, what is known/unknown)

### Analysis
(the substantive analysis from the sub-agent)

### CFO Recommendation
(concrete, actionable next steps)

### Risks & Flags
(any financial risks, red flags, or uncertainties)

Format: clean markdown. No meta-commentary about the synthesis process.
"""

    env = {
        "HOME": os.environ.get("HOME", "/home/zoltan"),
        "ANTHROPIC_API_KEY": Config.ANTHROPIC_AUTH_TOKEN or "",
        "ANTHROPIC_BASE_URL": Config.ANTHROPIC_BASE_URL or "https://chat.ultimateai.org",
    }

    try:
        result = subprocess.run(
            [
                str(CLAUDE_BIN),
                "-p",
                synthesis_prompt,  # positional arg (not stdin)
                "--model", "MiniMax-M2.7",
                "--output-format", "json",
                "--bare",  # non-interactive mode (no TTY required)
            ],
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )

        raw = result.stdout.strip()
        try:
            parsed = json.loads(raw)
            text = parsed.get("result", parsed.get("content", ""))
        except json.JSONDecodeError:
            text = re.sub(r"^```json\s*", "", raw, flags=re.IGNORECASE)
            text = re.sub(r"^```\s*", "", text)
            text = text.strip().strip("`")
            try:
                inner = json.loads(text)
                text = inner.get("result", inner.get("content", text))
            except json.JSONDecodeError:
                text = text

        return text

    except Exception as e:
        return f"[SYNTHESIS ERROR] {type(e).__name__}: {e}\n\nOriginal sub-agent result:\n{sub_agent_result}"

    except subprocess.TimeoutExpired:
        return f"[SYNTHESIS TIMEOUT]\n\nOriginal sub-agent result:\n{sub_agent_result}"


def _save_to_vault(content: str, task: str, domain: str) -> str:
    """Save CFO analysis to vault with YAML frontmatter."""
    safe_task = task[:50].replace("/", "-").replace(" ", "_").replace("'", "")
    filename = f"{date.today().isoformat()}_{safe_task}.md"

    domain_folders = {
        "financial_analysis": "financial_analysis",
        "pricing_strategy": "pricing",
        "roi_analysis": "roi_reports",
    }
    folder = domain_folders.get(domain, "analyses")
    save_path = VAULT_ROOT / folder / filename

    frontmatter = f"""---
title: "{task}"
type: {domain}
created: {date.today().isoformat()}
tags: [cfo, aestas]
---

"""
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(frontmatter + content)

    return str(save_path)


# ── Main entry point ───────────────────────────────────────────────────────────

def run_cfo_task(question: str) -> dict:
    """Process a CFO task: classify → sub-agent → synthesize → save vault.

    Args:
        question: The financial question or task

    Returns:
        dict with keys: result (str), vault_path (str), domain (str)
    """
    domain = _classify_question(question)

    # Step 1: Call appropriate sub-agent
    sub_result = _call_sub_agent(domain, question)

    # Step 2: Synthesize into final output
    final_result = _synthesize_analysis(domain, sub_result, question)

    # Step 3: Save to vault
    vault_path = _save_to_vault(final_result, question, domain)

    return {
        "result": final_result,
        "vault_path": vault_path,
        "domain": domain,
        "question": question,
    }


# ── Sub-agents export (from original file) ──────────────────────────────────
from crewai import Agent
from crewai.llm import LLM
from crewai_tools import DirectoryReadTool, FileReadTool, TavilySearchTool

if Config.ANTHROPIC_AUTH_TOKEN:
    os.environ["ANTHROPIC_API_KEY"] = Config.ANTHROPIC_AUTH_TOKEN
if Config.ANTHROPIC_BASE_URL:
    os.environ["ANTHROPIC_BASE_URL"] = Config.ANTHROPIC_BASE_URL.rstrip("/v1")


def get_llm():
    return LLM(
        provider="anthropic",
        model="MiniMax-M2.7",
        api_key=Config.ANTHROPIC_AUTH_TOKEN,
        base_url=Config.ANTHROPIC_BASE_URL.rstrip("/v1") if Config.ANTHROPIC_BASE_URL else "https://chat.ultimateai.org",
    )


class FinancialAnalysisAgent(Agent):
    def __init__(self):
        super().__init__(
            role="Financial Analyst",
            goal="Analyze financial viability, unit economics, and revenue model strength",
            backstory=(
                "You are a rigorous financial analyst with deep expertise in P&L analysis, "
                "SaaS metrics, and unit economics. You've spent 15+ years helping startups "
                "and growth-stage companies understand their economic engine — what drives "
                "margins, where value leaks, and whether the business model is sustainable. "
                "You speak fluent SaaS: MRR, ARR, churn, LTV, CAC, payback period, NRR. "
                "You believe every business question has a financial answer — you just need "
                "the right data and assumptions. You challenge magical thinking with "
                "hard numbers and scenario modeling. "
                "You have live access to the Aestas Second Brain vault for domain context."
            ),
            verbose=Config.VERBOSE,
            tools=[FileReadTool(), TavilySearchTool()],
            llm=get_llm(),
        )
        from src.tools import AgentBusTool, SecondBrainKnowledgeTool
        self.tools.append(AgentBusTool())
        self.tools.append(SecondBrainKnowledgeTool())


class PricingStrategyAgent(Agent):
    def __init__(self):
        super().__init__(
            role="Pricing Strategist",
            goal="Evaluate pricing strategies and their strategic implications",
            backstory=(
                "You are a pricing strategist who understands that price is not just a number — "
                "it's a strategic signal to the market. With 12+ years of experience in B2B "
                "and B2C pricing, you've helped companies double MRR through smart pricing "
                "changes alone. You know the psychology of pricing: anchoring, decoys, "
                "feature gating, and why a 20% price increase sometimes increases volume. "
                "You can model subscription vs. one-time vs. freemium trade-offs and show "
                "exactly how each affects LTV, CAC, and cash flow timing. You always ask: "
                "'What problem does this pricing solve for the customer, and what is that worth?' "
                "You have live access to the Aestas Second Brain vault for domain context."
            ),
            verbose=Config.VERBOSE,
            tools=[FileReadTool(), TavilySearchTool()],
            llm=get_llm(),
        )
        from src.tools import AgentBusTool, SecondBrainKnowledgeTool
        self.tools.append(AgentBusTool())
        self.tools.append(SecondBrainKnowledgeTool())


class ROIAnalysisAgent(Agent):
    def __init__(self):
        super().__init__(
            role="ROI Analyst",
            goal="Quantify ROI, payback periods, and long-term value metrics",
            backstory=(
                "You are a ROI analyst who turns investment decisions into numbers. With "
                "10+ years in corporate finance and venture-backed startups, you've "
                "evaluated everything from marketing campaigns to infrastructure migrations "
                "to M&A opportunities. You build detailed financial models showing "
                "payback period, ROI, IRR, and NPV — with sensitivity analysis on every "
                "key assumption. You know the LTV/CAC ratio is the heartbeat of a SaaS "
                "business and can spot when unit economics are heading for trouble. "
                "You believe in showing your work: every number traced back to "
                "an assumption, every conclusion stress-tested against scenarios. "
                "You have live access to the Aestas Second Brain vault for domain context."
            ),
            verbose=Config.VERBOSE,
            tools=[FileReadTool(), TavilySearchTool()],
            llm=get_llm(),
        )
        from src.tools import AgentBusTool, SecondBrainKnowledgeTool
        self.tools.append(AgentBusTool())
        self.tools.append(SecondBrainKnowledgeTool())


def get_cfo_agents():
    return [FinancialAnalysisAgent(), PricingStrategyAgent(), ROIAnalysisAgent()]
