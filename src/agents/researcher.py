"""Researcher Agent — Market & Business Research Intelligence.

This agent conducts deep market research, competitive analysis, and business
intelligence gathering for Aestas Healthcare ventures.

Uses RESEARCHER_PROMPT.md for focused research framework knowledge.

Vault path: /home/zoltan/srv/vault/Second Brain/raw/Aestas_Researcher/
"""

from crewai import Agent
from crewai.llm import LLM
from crewai.tools import BaseTool
from typing import Optional
from pathlib import Path
import json

# Lazy imports for heavy dependencies
def _get_config():
    from ..config import Config
    return Config

def _get_llm():
    config = _get_config()
    return LLM(
        provider="anthropic",
        model="MiniMax-M2.7",
        api_key=config.ANTHROPIC_AUTH_TOKEN,
        base_url=config.ANTHROPIC_BASE_URL.rstrip("/v1") if config.ANTHROPIC_BASE_URL else "https://chat.ultimateai.org",
    )


# =============================================================================
# PATHS
# =============================================================================

VAULT_ROOT = Path.home() / "srv" / "vault" / "Second Brain" / "raw"
VAULT_RESEARCHER_PATH = VAULT_ROOT / "Aestas_Researcher"

# Researcher Prompt path
RESEARCHER_PROMPT_PATH = Path("/home/zoltan/srv/crewai/ai_council/src/prompts/RESEARCHER_PARTNER_PROMPT.md")
RESEARCHER_TASK_PROMPT_PATH = Path("/home/zoltan/srv/crewai/ai_council/src/prompts/RESEARCHER_TASK_PROMPT.md")


def _load_researcher_prompt() -> str:
    """Load the RESEARCHER_TASK_PROMPT.md (trimmed ~50 lines) for fast task execution."""
    if RESEARCHER_TASK_PROMPT_PATH.exists():
        return RESEARCHER_TASK_PROMPT_PATH.read_text(encoding="utf-8")
    if RESEARCHER_PROMPT_PATH.exists():
        return RESEARCHER_PROMPT_PATH.read_text(encoding="utf-8")
    return ""


# =============================================================================
# VAULT STORAGE TOOL
# =============================================================================

class ResearcherVaultStorageTool(BaseTool):
    """Saves research documents and analyses to the vault folder structure.

    Documents are saved with YAML frontmatter containing metadata.
    Folder: VAULT_ROOT / Aestas_Researcher / {sub_folder} / {timestamp}_{title}.md
    """

    name: str = "ResearcherVaultStorage"
    description: str = (
        "Saves research documents, analyses, and reports to the vault. "
        "Input should be a JSON string with keys: content (markdown), title (string), "
        "and optional metadata (dict with doc_type, tags, region)."
    )

    agent_folder: str = "Aestas_Researcher"
    sub_folder: str = "research"

    def _run(self, content: str, title: str, metadata: Optional[dict] = None) -> str:
        """Save content to vault folder.

        Args:
            content: The document content to save (markdown)
            title: Short descriptive title for the document
            metadata: Optional dict with keys: doc_type, tags, region
        """
        from datetime import datetime

        # Determine folder from metadata or instance defaults
        doc_type = metadata.get("doc_type", self.sub_folder) if metadata else self.sub_folder
        region = metadata.get("region", "general")

        # Build folder path
        if region and region != "general":
            folder = VAULT_RESEARCHER_PATH / region / doc_type
        else:
            folder = VAULT_RESEARCHER_PATH / doc_type

        folder.mkdir(parents=True, exist_ok=True)

        # Create slug for filename
        slug = title.lower().replace(" ", "_").replace("/", "-").replace("\\", "-")[:50]
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug}.md"
        path = folder / filename

        # Build tags string for frontmatter
        tags_list = metadata.get("tags", []) if metadata else []
        tags_str = ", ".join(tags_list) if tags_list else ""

        # Write with frontmatter header
        frontmatter = f"""---
title: {title}
agent: Researcher
doc_type: {doc_type}
region: {region}
timestamp: {datetime.now().isoformat()}
tags: [{tags_str}]
---

"""
        path.write_text(frontmatter + content, encoding="utf-8")
        return f"Saved: {path.relative_to(VAULT_ROOT)}"


# =============================================================================
# WEB SEARCH TOOL
# =============================================================================

class WebSearchTool(BaseTool):
    """Web search tool for market research and competitive analysis.

    Use to search for market data, competitor information, industry trends,
    and business intelligence.
    """

    name: str = "WebSearch"
    description: str = (
        "Search the web for market research, competitive analysis, and business intelligence. "
        "Use for: market size data, competitor analysis, industry trends, "
        "customer demographics, pricing strategies. "
        "Input: search query string (e.g., 'healthcare market Hungary 2024' or "
        "'competitor analysis medical devices EU')."
    )

    def _run(self, query: str = "") -> str:
        """Search for market research information.

        Args:
            query: Search query string

        Returns:
            JSON string with search results
        """
        try:
            from crewai_tools import TavilySearchTool as CrewTavilySearch
            tool = CrewTavilySearch()
            return tool.run(query=query)
        except ImportError:
            return '{"error": "crewai_tools not installed. Run: pip install crewai-tools"}'
        except Exception as e:
            return f'{{"error": "{str(e)}"}}'


# =============================================================================
# INDUSTRY REPORT TOOL
# =============================================================================

class IndustryReportTool(BaseTool):
    """Reads industry reports and market analyses from the vault.

    This is the primary local database for industry reports and market analyses.
    """

    name: str = "IndustryReportReader"
    description: str = (
        "Reads industry reports and market analyses from the vault. "
        "Use this to answer questions about market sizes, industry trends, "
        "competitor profiles, and business opportunities. Input: search query or topic."
    )

    def _run(self, query: str = "") -> str:
        """Search the industry reports database.

        Args:
            query: Topic or keyword to search for

        Returns:
            Relevant sections from industry reports
        """
        reports_dir = VAULT_ROOT / "Aestas_Researcher" / "reports"
        if not reports_dir.exists():
            return f'{{"error": "Industry reports directory not found at {reports_dir}"}}'

        try:
            # Search through all .md files in the reports directory
            results = []
            for md_file in reports_dir.rglob("*.md"):
                content = md_file.read_text(encoding="utf-8")
                if query.lower() in content.lower():
                    results.append(f"## {md_file.name}\n\n{content[:2000]}")

            if results:
                return "\n\n---\n\n".join(results[:5])
            return "No relevant industry reports found."
        except Exception as e:
            return f'{{"error": "{str(e)}"}}'


# =============================================================================
# AGENT BUS TOOL
# =============================================================================

class AgentBusTool(BaseTool):
    """Send/receive messages to/from other agents via Redis pub/sub."""

    name: str = "AgentBus"
    description: str = (
        "Send a message to another agent or receive messages. "
        "Use to: request_info (ask another agent for information), "
        "provide_info (send results back), task_complete (notify completion). "
        "Format: send to='AgentName' action='send' data={...} "
        "Or recv timeout=30 to wait for a response."
    )

    def _run(
        self,
        action: str = "send",
        to: str = "",
        from_: str = "Researcher",
        data: str = "{}",
        timeout: int = 30,
        recv_agent: str = "Researcher"
    ) -> str:
        """Run the AgentBus tool.

        Args:
            action: 'send' or 'recv'
            to: Recipient agent name (for send)
            from_: Sender agent name (for send)
            data: JSON payload (for send)
            timeout: Seconds to wait for recv
            recv_agent: Agent name to subscribe as for recv
        """
        from src.agent_bus import AgentBus

        bus = AgentBus()

        if action == "send":
            try:
                parsed = json.loads(data) if isinstance(data, str) and data.startswith("{") else {}
            except (json.JSONDecodeError, ValueError):
                parsed = {"raw": data}
            msg_id = bus.send(to=to, from_=from_, action=action, data=parsed)
            return f"Message sent: {msg_id}"

        elif action == "recv":
            bus = AgentBus()
            msg = bus.recv(agent_name=recv_agent, timeout=timeout)
            if msg:
                return json.dumps(msg, indent=2)
            return "No message received."

        return "Unknown action. Use send or recv."


# =============================================================================
# RESEARCHER AGENT
# =============================================================================

class Researcher(Agent):
    """Researcher agent for Market & Business Intelligence.

    The Researcher provides:
    - Market research and analysis
    - Competitive intelligence gathering
    - Industry trend monitoring
    - Business opportunity identification
    - Customer and demographic analysis

    Tools:
    - ResearcherVaultStorageTool: Save research to vault
    - WebSearchTool: Search for market data online
    - IndustryReportTool: Query local industry reports database
    - AgentBusTool: Communicate with other agents
    """

    def __init__(self):
        super().__init__(
            role="Market Research Analyst",
            goal=(
                "Provide comprehensive market research and competitive intelligence "
                "for Aestas Healthcare ventures. Gather market data, analyze competitors, "
                "identify business opportunities, and deliver actionable insights "
                "that inform strategic decisions."
            ),
            backstory=(
                "You are a seasoned market research analyst with deep expertise in "
                "healthcare markets, particularly in Central and Eastern Europe. "
                "You have 10+ years of experience conducting market assessments, "
                "competitive analyses, and business intelligence research for "
                "healthcare companies, pharmaceutical firms, and medical device "
                "manufacturers. You speak Hungarian natively and are fluent in English, "
                "allowing you to access both local Hungarian sources and international "
                "market data. You track market trends, competitor movements, "
                "regulatory changes, and emerging opportunities across the healthcare sector. "
                "You believe that data-driven decisions are the foundation of business success. "
                "You have live access to the Aestas Second Brain vault for domain context."
            ),
            verbose=_get_config().VERBOSE,
            tools=[
                ResearcherVaultStorageTool(),
                WebSearchTool(),
                IndustryReportTool(),
                AgentBusTool(),
            ],
            llm=_get_llm(),
        )
        from src.tools.second_brain_tool import SecondBrainKnowledgeTool
        self.tools.append(SecondBrainKnowledgeTool())


def get_researcher(tools: list = None) -> Researcher:
    """Factory function to create the Researcher agent.

    Args:
        tools: Override tools list. Pass empty list [] when using Researcher as a
               hierarchical manager agent (CrewAI forbids manager agents having tools).

    Returns:
        Researcher instance
    """
    if tools is not None:
        class ResearcherManager(Researcher):
            def __init__(self):
                super().__init__()
                object.__setattr__(self, 'tools', tools)
        return ResearcherManager()
    return Researcher()


# =============================================================================
# STANDALONE RESEARCH TASK RUNNER
# =============================================================================

def _do_tavily_search(query: str, max_results: int = 5) -> str:
    """Perform a Tavily web search and return formatted results using requests."""
    import requests
    import os
    key = os.environ.get("TAVILY_API_KEY", "")
    if not key:
        return "[Search error: No TAVILY_API_KEY configured]"
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {key}"},
            json={"query": query, "max_results": max_results, "include_answer": False, "include_images": False},
            timeout=(5, 15),
        )
        resp.raise_for_status()
        parsed = resp.json()
        if "results" in parsed:
            lines = []
            for r in parsed["results"][:max_results]:
                lines.append(f"- {r.get('title', 'No title')}: {r.get('url', '')}")
                if r.get('content'):
                    lines.append(f"  {r['content'][:300]}")
            return "\n".join(lines)
        return str(parsed)[:1000]
    except Exception as e:
        return f"[Search error: {e}]"


def _plan_research_subquestions(question: str) -> list[str]:
    """Use Claude Code to plan research sub-questions, then search each via Tavily."""
    researcher_prompt = _load_researcher_prompt()
    planning_prompt = (
        "You are Researcher for Aestas Healthcare. Break this research question into 3-5 specific sub-questions.\n"
        "Return ONLY a JSON list of sub-question strings.\n\n"
        f"QUESTION: {question}\n\n"
        "Return format: [\"sub-question 1\", \"sub-question 2\", ...]"
    )
    env = {
        "ANTHROPIC_API_KEY": _get_config().ANTHROPIC_AUTH_TOKEN or "",
        "ANTHROPIC_BASE_URL": "https://chat.ultimateai.org",
    }
    cmd = [
        str(Path.home() / ".local" / "bin" / "claude"),
        "-p", "--model", "MiniMax-M2.7", "--output-format", "json",
    ]
    try:
        result = subprocess.run(
            cmd, input=planning_prompt, capture_output=True, text=True,
            timeout=60, env={**__import__("os").environ, **env},
        )
        if result.returncode != 0:
            return [question]
        raw = result.stdout.strip()
        parsed = json.loads(raw)
        text = parsed.get("result", raw)
        # Strip fences
        text = re.sub(r"\`\`\`(?:json)?\s*", "", text.strip()).strip().rstrip("`")
        subquestions = json.loads(text)
        if isinstance(subquestions, list):
            return subquestions[:5]
    except Exception:
        pass
    return [question]


def run_researcher_task(question: str) -> dict:
    """Run a research task: plan sub-questions, search via Tavily, synthesize with Claude Code.

    Pipeline:
    1. Plan 3-5 research sub-questions via Claude Code
    2. Search each via Tavily (in Python, real web access)
    3. Synthesize findings into cited report via Claude Code
    4. Save to vault
    """
    import re
    import subprocess
    from datetime import datetime

    # Pre-fetch relevant vault context
    try:
        from src.tools.second_brain_tool import SecondBrainKnowledgeTool
        vault_tool = SecondBrainKnowledgeTool()
        vault_ctx = vault_tool._run(query=question, sections=["Researcher", "CMO"])
        if vault_ctx and "not found" not in vault_ctx.lower()[:100] and "No results" not in vault_ctx:
            vault_section = f"\n\n## Relevant Context from Second Brain Vault\n{vault_ctx}\n"
        else:
            vault_section = ""
    except Exception:
        vault_section = ""

    # 1. Plan sub-questions
    subquestions = _plan_research_subquestions(question)

    # 2. Search each sub-question via Tavily
    search_results = []
    for i, sq in enumerate(subquestions, 1):
        search_results.append(f"\n## Search {i}: {sq}")
        # Try 2-3 keyword variations
        variations = [
            sq,
            sq + " Hungary EU 2025 2026",
            sq + " market size competitors",
        ]
        for variation in variations[:2]:
            results = _do_tavily_search(variation, max_results=4)
            search_results.append(f"\nQuery: {variation}\n{results}")

    all_searches = "\n".join(search_results)

    # 3. Synthesize via Claude Code
    researcher_prompt = _load_researcher_prompt()
    synthesis_prompt = (
        "You are Researcher for Aestas Healthcare.\n\n"
        "You have conducted web searches. Synthesize the findings into a research report.\n\n"
        f"ORIGINAL QUESTION: {question}\n\n"
        f"SEARCH RESULTS:\n{all_searches}\n"
        f"RESEARCHER FRAMEWORK:\n{researcher_prompt}\n"
        + vault_section + "\n"
        "Using the search results above, write a comprehensive research report."
    )

    env = {
        "ANTHROPIC_API_KEY": _get_config().ANTHROPIC_AUTH_TOKEN or "",
        "ANTHROPIC_BASE_URL": "https://chat.ultimateai.org",
    }
    cmd = [
        str(Path.home() / ".local" / "bin" / "claude"),
        "-p", "--model", "MiniMax-M2.7", "--output-format", "json",
    ]
    try:
        result = subprocess.run(
            cmd, input=synthesis_prompt, capture_output=True, text=True,
            timeout=300, env={**__import__("os").environ, **env},
        )
    except subprocess.TimeoutExpired:
        return {"result": "[ERROR] Synthesis timed out after 300s", "vault_path": None}
    except FileNotFoundError:
        return {"result": f"[ERROR] Claude Code binary not found", "vault_path": None}

    if result.returncode != 0:
        return {"result": f"[ERROR] Claude Code exit {result.returncode}: {result.stderr}", "vault_path": None}

    raw = result.stdout.strip()
    try:
        parsed = json.loads(raw)
        result_text = parsed.get("result", "")
        result_text = re.sub(r"\`\`\`(?:json)?\s*", "", result_text.strip()).strip().rstrip("`")
    except json.JSONDecodeError:
        result_text = re.sub(r"\`\`\`(?:json)?\s*", "", raw).strip().rstrip("`")

    # 4. Save to vault
    vault_path = None
    try:
        VAULT_RESEARCHER_PATH.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        date_str = now.strftime("%Y%m%d")
        slug = re.sub(r"[^\w\s-]", "", question)[:60].replace(" ", "_").lower()
        filename = f"{date_str}_{slug}.md"
        vault_file = VAULT_RESEARCHER_PATH / filename
        frontmatter = f"---\ndate: {now.isoformat(timespec='seconds')}\nquestion: {question}\nmodel: MiniMax-M2.7\nagent: Researcher\n---\n\n"
        vault_file.write_text(frontmatter + result_text, encoding="utf-8")
        vault_path = str(vault_file)
    except Exception:
        pass

    return {"result": result_text, "vault_path": vault_path}
