"""CTO Operational Agent — run_cto_task entry point + sub-agent task prompts.

run_cto_task() is the daemon entry point. It classifies the incoming question
into one of three sub-agent domains (TechStackEvaluator, BuildVsBuyAgent, ArchitectureReviewAgent),
calls Claude Code with the appropriate sub-agent prompt, synthesizes the result,
and saves to vault.

Vault: /home/zoltan/srv/vault/Second Brain/raw/Aestas_CTO/
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

VAULT_ROOT = Path("/home/zoltan/srv/vault/Second Brain/raw/Aestas_CTO")
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

_SUB_AGENT_PROMPTS = {
    "tech_stack": """You are TechStackEvaluator — assesses technology choices, stack maturity, and maintenance burden.

Aestas Healthcare context (known):
- Business: subscription telemedicine (B2C + B2B)
- Markets: Cyprus, Sweden, Hungary (cross-border GP)
- Stage: early growth
- Team: small, founder-led with some contractors
- Constraints: limited budget, compliance-heavy (GDPR, medical data)

Task: {question}

Provide a structured technology stack evaluation covering:
1. The technology choice described and context
2. Maturity and community assessment
3. Maintenance burden and technical debt implications
4. Developer productivity impact
5. Stage-appropriateness for early-growth company
6. Recommended assessment (adopt / pilot / avoid)
7. Key risks

Be specific. Name alternatives where relevant.""",

    "build_vs_buy": """You are BuildVsBuyAgent — analyzes build vs. buy vs. integrate decisions.

Aestas Healthcare context (known):
- Business: subscription telemedicine (B2C + B2B)
- Markets: Cyprus, Sweden, Hungary (cross-border GP)
- Stage: early growth
- Team: small, founder-led with some contractors
- Compliance: GDPR, medical data handling

Task: {question}

Provide a structured build vs. buy analysis covering:
1. Problem or need clearly stated
2. Core vs. commodity determination
3. Build option assessment (cost, time, skills required)
4. Buy option assessment (vendor, cost, lock-in risk)
5. Integrate option assessment (existing tools + minimal customization)
6. 3-year TCO comparison
7. Lock-in and exit risk
8. Recommendation with rationale

Apply the framework rigorously. Every conclusion backed by explicit assumptions.""",

    "architecture": """You are ArchitectureReviewAgent — reviews system architecture for scalability, security, and cost.

Aestas Healthcare context (known):
- Business: subscription telemedicine (B2C + B2B)
- Markets: Cyprus, Sweden, Hungary (cross-border GP)
- Stage: early growth
- Compliance: GDPR, medical data (patient records)
- User scale: currently small, planning growth

Task: {question}

Provide a structured architecture review covering:
1. Current architecture described (or N/A for new systems)
2. Scalability assessment
3. Security and compliance posture (GDPR, medical data)
4. Cost efficiency (cloud, infrastructure)
5. Maintainability (can the team keep it running?)
6. Key architectural risks or anti-patterns
7. Recommended improvements (prioritized)

Frame recommendations as: immediate fixes vs. future improvements.""",
}

# Keyword-based task classifier
_TASK_KEYWORDS = {
    "tech_stack": [
        "tech stack", "technology stack", "framework", "library", "language",
        "database", "frontend", "backend", "api", "tool", "software",
        "open source", "commercial", "saas tool", "hosting", "cloud",
        "aws", "gcp", "azure", "postgres", "react", "vue", "django",
        "rails", "node", "python", "rust", "go", "java",
    ],
    "build_vs_buy": [
        "build vs buy", "build vs. buy", "build or buy", "outsource",
        "off the shelf", "third party", "vendor", "procurement",
        "make vs buy", "tco", "total cost", "custom development",
        "integrate", "integration",
    ],
    "architecture": [
        "architecture", "system design", "scalability", "microservices",
        "monolith", "api gateway", "load balancer", "caching", "cdn",
        "database design", "schema", "refactor", "migration",
        "infrastructure", "deployment", "ci/cd", "container",
        "docker", "kubernetes", "serverless", "fault tolerance",
        "availability", "disaster recovery", "backup",
    ],
}


def _classify_question(question: str) -> str:
    """Classify a question into a sub-agent domain by keyword scoring."""
    q_lower = question.lower()
    scores = {}
    for domain, keywords in _TASK_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in q_lower)
        scores[domain] = score

    if max(scores.values()) > 0:
        return max(scores, key=scores.get)
    return "tech_stack"


def _call_sub_agent(domain: str, question: str) -> str:
    """Call Claude Code subprocess with the appropriate sub-agent prompt."""
    prompt_template = _SUB_AGENT_PROMPTS.get(domain, _SUB_AGENT_PROMPTS["tech_stack"])

    # Pre-fetch relevant vault context
    vault_ctx = _get_vault_context(question, sections=["CTO"])

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

    except subprocess.TimeoutExpired:
        return f"[TIMEOUT] Claude Code timed out after 300s for domain: {domain}"
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}"


def _synthesize_analysis(domain: str, sub_agent_result: str, question: str) -> str:
    """Synthesize the sub-agent result into a final CTO analysis."""
    domain_titles = {
        "tech_stack": "Technology Stack Evaluation",
        "build_vs_buy": "Build vs. Buy Analysis",
        "architecture": "Architecture Review",
    }

    synthesis_prompt = f"""Synthesize the following CTO sub-agent analysis into a final structured output.

ORIGINAL QUESTION: {question}
SUB-AGENT DOMAIN: {domain_titles.get(domain, domain)}

SUB-AGENT ANALYSIS:
{sub_agent_result}

Produce a final CTO analysis in this format:
## CTO Analysis: [brief title from question]

### Context
(what is the technology decision at hand)

### Analysis
(substantive analysis from the sub-agent)

### CTO Recommendation
(concrete, actionable next steps — what to build/buy/change)

### Risks & Trade-offs
(any risks, trade-offs, or limitations)

### Timeline & Priority
(if assessable: immediate vs. short-term vs. long-term)

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
    """Save CTO analysis to vault with YAML frontmatter."""
    safe_task = task[:50].replace("/", "-").replace(" ", "_").replace("'", "")
    filename = f"{date.today().isoformat()}_{safe_task}.md"

    domain_folders = {
        "tech_stack": "stack_evaluations",
        "build_vs_buy": "build_vs_buy",
        "architecture": "architecture_reviews",
    }
    folder = domain_folders.get(domain, "tech_decisions")
    save_path = VAULT_ROOT / folder / filename

    frontmatter = f"""---
title: "{task}"
type: {domain}
created: {date.today().isoformat()}
tags: [cto, aestas]
---

"""
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(frontmatter + content)

    return str(save_path)


# ── Main entry point ───────────────────────────────────────────────────────────

def run_cto_task(question: str) -> dict:
    """Process a CTO task: classify → sub-agent → synthesize → save vault.

    Args:
        question: The technology question or task

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


class TechStackEvaluator(Agent):
    def __init__(self):
        super().__init__(
            role="Tech Stack Evaluator",
            goal="Evaluate technology stack decisions and their long-term implications",
            backstory=(
                "You are a technology evaluator who has seen countless stacks over 15+ years — "
                "from greenfield startups to legacy enterprise migrations. You understand "
                "that 'best' technology is always context-dependent: team skills, scale, "
                "timeline, and budget all shape the right choice. You've helped companies "
                "avoid the trap of using exciting-but-risky tech that nobody on the team "
                "can maintain. You assess maturity, community support, hiring pool size, "
                "and the hidden maintenance cost of 'clever' solutions. You bias toward "
                "boring technology that works and can be maintained by average engineers."
            ),
            verbose=Config.VERBOSE,
            tools=[FileReadTool(), TavilySearchTool(), DirectoryReadTool()],
            llm=get_llm(),
        )
        from src.tools import AgentBusTool
        self.tools.append(AgentBusTool())


class BuildVsBuyAgent(Agent):
    def __init__(self):
        super().__init__(
            role="Build vs. Buy Analyst",
            goal="Structure build vs. buy vs. integrate decisions systematically",
            backstory=(
                "You are a build vs. buy specialist who has advised on hundreds of technology "
                "procurement decisions. You know the seductive trap of 'we should build it "
                "ourselves' — the initial excitement, the scope creep, the maintenance burden "
                "that never ends. You've also seen companies fail by over-relying on vendors "
                "who changed pricing, pivoted, or got acquired. You apply a rigorous "
                "framework: Is it core to differentiation? Can we hire/keep the skills? "
                "What's the 3-year TCO? What's the lock-in risk? You default to 'buy' "
                "for everything that's not a competitive advantage and can prove it with math."
            ),
            verbose=Config.VERBOSE,
            tools=[FileReadTool(), TavilySearchTool()],
            llm=get_llm(),
        )
        from src.tools import AgentBusTool
        self.tools.append(AgentBusTool())


class ArchitectureReviewAgent(Agent):
    def __init__(self):
        super().__init__(
            role="Architecture Reviewer",
            goal="Review and improve system architecture decisions",
            backstory=(
                "You are an architecture reviewer who has designed and critiqued systems "
                "spanning from 100 users to 100 million. You understand the evolution "
                "journey: the monolith that becomes a modular monolith, the services "
                "that emerge when they genuinely need to, and the microservices that "
                "should never have been split. You review architecture through four lenses: "
                "Does it scale? Is it secure? Is it cost-efficient? Can the team maintain it? "
                "You spot single points of failure, over-engineered solutions, and the "
                "tech debt that compounds silently until it becomes a crisis. You believe "
                "the best architecture is the simplest one that meets current requirements "
                "without foreclosing future options."
            ),
            verbose=Config.VERBOSE,
            tools=[FileReadTool(), TavilySearchTool(), DirectoryReadTool()],
            llm=get_llm(),
        )
        from src.tools import AgentBusTool
        self.tools.append(AgentBusTool())


def get_cto_agents():
    return [TechStackEvaluator(), BuildVsBuyAgent(), ArchitectureReviewAgent()]
