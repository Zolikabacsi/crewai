"""COO Operational Agent — run_coo_task entry point + sub-agent task prompts.

run_coo_task() is the daemon entry point. It classifies the incoming question
into one of three sub-agent domains (ProcessDesigner, CapacityPlanner, RACIMapper),
calls Claude Code with the appropriate sub-agent prompt, synthesizes the result,
and saves to vault.

Vault: /home/zoltan/srv/vault/Second Brain/raw/Aestas_COO/
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

VAULT_ROOT = Path("/home/zoltan/srv/vault/Second Brain/raw/Aestas_COO")
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
    "process_design": """You are ProcessDesigner — designs efficient, scalable operational workflows.

Aestas Healthcare context (known):
- Business: subscription telemedicine (B2C + B2B)
- Markets: Cyprus, Sweden, Hungary (cross-border GP)
- Team: small, founder-led with some contractors
- Compliance: GDPR, medical data handling

Task: {question}

Provide a structured process design covering:
1. Current state (if applicable) — what's working, what's not
2. Process goal clearly stated
3. Key steps in the proposed workflow
4. Decision nodes and quality gates
5. Roles and responsibilities within the process
6. Scalability: can this run without the founder?
7. Automation opportunities
8. Risk points and failure modes

Design for minimum viable: don't over-engineer. Every step must justify its existence.""",

    "capacity_planning": """You are CapacityPlanner — assesses team capacity, hiring needs, and workload distribution.

Aestas Healthcare context (known):
- Business: subscription telemedicine (B2C + B2B)
- Markets: Cyprus, Sweden, Hungary (cross-border GP)
- Stage: early growth
- Team: small, founder-led with some contractors

Task: {question}

Provide a structured capacity analysis covering:
1. Current team capacity snapshot (who does what)
2. Workload analysis — what's overflowing, what's underutilized
3. Bottleneck identification — what's constraining everything else
4. Hiring/contractor options to address gaps
5. Fractional vs. full-time vs. contractor trade-offs
6. Timeline and priority for addressing capacity issues
7. Risk: what happens if capacity isn't expanded?

Be specific: name roles, timelines, cost implications where possible.""",

    "raci_mapping": """You are RACIMapper — clarifies decision rights and accountability across teams.

Aestas Healthcare context (known):
- Business: subscription telemedicine (B2C + B2B)
- Markets: Cyprus, Sweden, Hungary (cross-border GP)
- Team: small, founder-led with some contractors
- Compliance: GDPR, medical data (patient records)

Task: {question}

Provide a structured RACI analysis covering:
1. Decision or deliverable clearly defined
2. Roles identified (who is involved)
3. RACI assignment for each step:
   - R = Responsible (does the work)
   - A = Accountable (final decision maker)
   - C = Consulted (provides input)
   - I = Informed (kept updated)
4. Escalation path defined (if A is unavailable?)
5. Key accountability gaps or overlaps identified
6. Recommended fixes

Rule: One A per deliverable. No deliverable with zero A.
""",
}

# Keyword-based task classifier
_TASK_KEYWORDS = {
    "process_design": [
        "process", "workflow", "sop", "standard operating", "runbook",
        "documentation", "automation", "handbook", "procedure",
        "protocol", "step by step", "sequence", "flow",
    ],
    "capacity_planning": [
        "capacity", "hiring", "team", "headcount", "workload",
        "bandwidth", "throughput", "resource", "contractor",
        "fractional", "full-time", "burnout", "overload",
        "utilization", "bottleneck", "scaling", "delegation",
    ],
    "raci_mapping": [
        "raci", "accountability", "responsibility", "decision rights",
        "ownership", "governance", "esca", "escalation",
        "who decides", "who is responsible", "role confusion",
        "matrix", "accountable", "accountability",
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
    return "process_design"


def _call_sub_agent(domain: str, question: str) -> str:
    """Call Claude Code subprocess with the appropriate sub-agent prompt."""
    prompt_template = _SUB_AGENT_PROMPTS.get(domain, _SUB_AGENT_PROMPTS["process_design"])

    # Pre-fetch relevant vault context
    vault_ctx = _get_vault_context(question, sections=["COO"])

    prompt = prompt_template.format(question=question) + vault_ctx

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
    """Synthesize the sub-agent result into a final COO analysis."""
    domain_titles = {
        "process_design": "Process Design",
        "capacity_planning": "Capacity Planning",
        "raci_mapping": "RACI Mapping",
    }

    synthesis_prompt = f"""Synthesize the following COO sub-agent analysis into a final structured output.

ORIGINAL QUESTION: {question}
SUB-AGENT DOMAIN: {domain_titles.get(domain, domain)}

SUB-AGENT ANALYSIS:
{sub_agent_result}

Produce a final COO analysis in this format:
## COO Analysis: [brief title from question]

### Context
(what operational challenge or question is being addressed)

### Analysis
(substantive analysis from the sub-agent)

### COO Recommendation
(concrete, actionable next steps)

### Risks & Trade-offs
(any operational risks, trade-offs, or limitations)

### Implementation Priority
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
    """Save COO analysis to vault with YAML frontmatter."""
    safe_task = task[:50].replace("/", "-").replace(" ", "_").replace("'", "")
    filename = f"{date.today().isoformat()}_{safe_task}.md"

    domain_folders = {
        "process_design": "processes",
        "capacity_planning": "capacity_plans",
        "raci_mapping": "raci_matrices",
    }
    folder = domain_folders.get(domain, "operational_docs")
    save_path = VAULT_ROOT / folder / filename

    frontmatter = f"""---
title: "{task}"
type: {domain}
created: {date.today().isoformat()}
tags: [coo, aestas]
---

"""
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(frontmatter + content)

    return str(save_path)


# ── Main entry point ───────────────────────────────────────────────────────────

def run_coo_task(question: str) -> dict:
    """Process a COO task: classify → sub-agent → synthesize → save vault.

    Args:
        question: The operational question or task

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


class ProcessDesigner(Agent):
    def __init__(self):
        super().__init__(
            role="Process Designer",
            goal="Design efficient, scalable operational processes",
            backstory=(
                "You are a process designer who has documented hundreds of workflows — "
                "from startup chaos to scaling operations. You believe the best process "
                "is the minimum one that solves the problem: not over-engineered, not "
                "under-documented. You've seen too many founders build elaborate systems "
                "for problems that don't exist yet, while leaving critical workflows "
                "completely undocumented. You design processes with the question: "
                "'Can this run without the founder?' You add documentation, decision "
                "nodes, and quality gates only where they actually prevent errors or "
                "enable scaling. You are ruthless about cutting process that doesn't "
                "add value."
            ),
            verbose=Config.VERBOSE,
            tools=[FileReadTool(), TavilySearchTool()],
            llm=get_llm(),
        )
        from src.tools import AgentBusTool
        self.tools.append(AgentBusTool())


class CapacityPlanner(Agent):
    def __init__(self):
        super().__init__(
            role="Capacity Planner",
            goal="Assess capacity requirements and resource allocation",
            backstory=(
                "You are a capacity planner who has sized teams from 2 to 200. You "
                "understand that the right team size is always context-dependent: "
                "stage, complexity, growth rate, and founder bandwidth all factor in. "
                "You've helped startups avoid the trap of over-hiring (burning cash "
                "on people without enough for them to do) and under-hiring (burning "
                "out the team on unsustainable workloads). You model capacity in terms "
                "of output, not headcount: what can this team actually ship per quarter? "
                "You identify the single bottleneck that constrains everything else and "
                "prescribe exactly what hiring or rebalancing would fix it."
            ),
            verbose=Config.VERBOSE,
            tools=[FileReadTool(), TavilySearchTool()],
            llm=get_llm(),
        )
        from src.tools import AgentBusTool
        self.tools.append(AgentBusTool())


class RACIMapper(Agent):
    def __init__(self):
        super().__init__(
            role="RACI Mapper",
            goal="Map decision rights and accountability across teams",
            backstory=(
                "You are a RACI specialist who has mapped accountability for hundreds of "
                "organizations. You believe most operational problems trace back to "
                "unclear ownership: nobody knows who decides, so nothing gets decided, "
                "or worse, two people fight over the same decision. You diagnose role "
                "confusion with surgical questions: Who makes the final call? Who is "
                "consulted? Who is informed? Who does the work? You've seen the same "
                "RACI mistakes made repeatedly: too many A's (accountable), vague R's "
                "(responsible), and generic C's (consulted) that add process without "
                "clarity. You build RACI matrices that actually work: one A per deliverable, "
                "clear escalation paths, and explicit decision rights at each level."
            ),
            verbose=Config.VERBOSE,
            tools=[FileReadTool(), TavilySearchTool()],
            llm=get_llm(),
        )
        from src.tools import AgentBusTool
        self.tools.append(AgentBusTool())


def get_coo_agents():
    return [ProcessDesigner(), CapacityPlanner(), RACIMapper()]
