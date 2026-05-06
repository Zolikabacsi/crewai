"""Clinical Guidelines Agent — Medical knowledge management for Aestas Healthcare.

This agent provides access to clinical guidelines from:
- Hungarian healthcare guidelines and protocols
- 1177 English medical database (Swedish patient education model)
- Medical research MOC (map of content)

Uses CLINICAL_PROMPT.md for focused clinical guideline synthesis methodology.

Tools:
- VaultStorageTool: Store and retrieve guidelines from vault
- TavilySearchTool: Search current medical guidelines online
- AgentBusTool: Communicate with other agents (CMO, CFO, COO, CTO)
"""

from crewai import Agent
from crewai.llm import LLM
from crewai.tools import BaseTool
from typing import Optional, List
from pathlib import Path
import json

# Configuration
VAULT_GUIDELINES_PATH = Path("/home/zoltan/srv/vault/Second Brain/raw/Aestas_CMedO/guidelines")
VAULT_SOURCE_PATHS = [
    Path("/home/zoltan/srv/vault/Second Brain/raw/Hungarian_Healthcare"),
    Path("/home/zoltan/srv/vault/Second Brain/raw/Medical database/1177 English"),
    Path("/home/zoltan/srv/vault/Second Brain/raw/Medical Research MOC.md"),
]

# Clinical Prompt path
CLINICAL_PROMPT_PATH = Path("/home/zoltan/srv/crewai/ai_council/src/prompts/CLINICAL_PROMPT.md")


def _load_clinical_prompt() -> str:
    """Load the CLINICAL_PROMPT.md for domain knowledge."""
    if CLINICAL_PROMPT_PATH.exists():
        return CLINICAL_PROMPT_PATH.read_text(encoding="utf-8")
    return ""

# Lazy-loaded imports for tools
_tavily_tool = None
_agent_bus_tool = None


def _get_llm():
    """Create LLM instance for ClinicalGuidelines agent with MiniMax-M2.7 model."""
    # Import here to avoid circular dependency
    from ..config import Config
    import os

    # Ensure environment is configured for custom endpoints
    if Config.ANTHROPIC_AUTH_TOKEN:
        os.environ["ANTHROPIC_API_KEY"] = Config.ANTHROPIC_AUTH_TOKEN
    if Config.ANTHROPIC_BASE_URL:
        os.environ["ANTHROPIC_BASE_URL"] = Config.ANTHROPIC_BASE_URL.rstrip("/v1")

    return LLM(
        provider="anthropic",
        model="MiniMax-M2.7",
        api_key=Config.ANTHROPIC_AUTH_TOKEN,
        base_url=Config.ANTHROPIC_BASE_URL.rstrip("/v1") if Config.ANTHROPIC_BASE_URL else "https://chat.ultimateai.org",
    )


class VaultStorageTool(BaseTool):
    """Store and retrieve clinical guidelines from the vault folder structure.

    Saves documents to: VAULT_GUIDELINES_PATH / {category} / {timestamp}_{title}.md
    """

    name: str = "VaultStorage"
    description: str = (
        "Store clinical guidelines and medical documents to the vault. "
        "Input should be a JSON string with keys: content (markdown), title (string), "
        "category (string, e.g. 'neurology', 'cardiology'), and optional tags (list)."
    )
    category: str = "general"  # Override: 'neurology', 'cardiology', etc.

    def _run(self, content: str, title: str, category: str = "general", tags: Optional[List[str]] = None) -> str:
        """Save content to vault guidelines folder.

        Args:
            content: The document content to save (markdown)
            title: Short descriptive title for the document
            category: Medical category (e.g., 'neurology', 'cardiology', 'general')
            tags: Optional list of tags for the document

        Returns:
            Path where document was saved
        """
        from datetime import datetime

        # Determine folder from category or instance default
        folder = VAULT_GUIDELINES_PATH / category
        folder.mkdir(parents=True, exist_ok=True)

        # Create slug for filename
        slug = title.lower().replace(" ", "_").replace("/", "-").replace("\\", "-")[:50]
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug}.md"
        path = folder / filename

        # Build tags string for frontmatter
        tags_str = ", ".join(tags) if tags else ""

        # Write with frontmatter header
        frontmatter = f"""---
title: {title}
category: {category}
type: clinical_guideline
timestamp: {datetime.now().isoformat()}
tags: [{tags_str}]
source: Aestas_CMedO
---

"""
        path.write_text(frontmatter + content, encoding="utf-8")
        return f"Saved: {path.relative_to(VAULT_GUIDELINES_PATH.parent.parent)}"


class VaultSearchTool(BaseTool):
    """Search clinical guidelines and medical documents in the vault.

    Searches across Hungarian healthcare, 1177 English database, and Medical Research MOC.
    """

    name: str = "VaultSearch"
    description: str = (
        "Search clinical guidelines and medical documents in the vault. "
        "Input should be a JSON string with keys: query (search string), "
        "sources (optional list of source folders to search), limit (max results, default 10)."
    )

    def _run(self, query: str, sources: Optional[List[str]] = None, limit: int = 10) -> str:
        """Search vault for relevant medical documents.

        Args:
            query: Search query string
            sources: List of source folders to search (defaults to all)
            limit: Maximum number of results

        Returns:
            JSON string with search results
        """
        import re

        results = []
        search_sources = sources or ["Hungarian_Healthcare", "1177 English", "Medical Research MOC"]

        for source in search_sources:
            if "Hungarian_Healthcare" in source:
                search_path = VAULT_SOURCE_PATHS[0]
            elif "1177" in source or "English" in source:
                search_path = VAULT_SOURCE_PATHS[1]
            elif "Research MOC" in source:
                search_path = VAULT_SOURCE_PATHS[2]
            else:
                continue

            # Search markdown files
            for md_file in search_path.rglob("*.md"):
                try:
                    content = md_file.read_text(encoding="utf-8")
                    # Simple relevance check - count query terms
                    query_lower = query.lower()
                    content_lower = content.lower()
                    matches = sum(1 for word in query_lower.split() if word in content_lower)
                    if matches > 0:
                        # Extract title from frontmatter or filename
                        title_match = re.search(r"^title:\s*(.+)$", content, re.MULTILINE)
                        title = title_match.group(1) if title_match else md_file.stem
                        # Get first paragraph as snippet
                        snippet = content.split("---")[-1].strip()[:200] if "---" in content else content[:200]
                        results.append({
                            "title": title,
                            "path": str(md_file.relative_to(Path.home() / "srv/vault")),
                            "source": source,
                            "relevance": matches,
                            "snippet": snippet,
                        })
                except Exception:
                    continue

        # Sort by relevance and limit
        results.sort(key=lambda x: x["relevance"], reverse=True)
        results = results[:limit]

        return json.dumps({"query": query, "results": results}, indent=2, ensure_ascii=False)


class VaultReadTool(BaseTool):
    """Read specific clinical guideline documents from the vault."""

    name: str = "VaultRead"
    description: str = (
        "Read a specific clinical guideline document from the vault. "
        "Input should be a JSON string with key: path (relative path from vault root, "
        "e.g. 'Second Brain/raw/Hungarian_Healthcare/filename.md')."
    )

    def _run(self, path: str, max_lines: int = 500) -> str:
        """Read a specific document from vault.

        Args:
            path: Relative path from vault root
            max_lines: Maximum number of lines to read

        Returns:
            Document content
        """
        from pathlib import Path

        vault_root = Path.home() / "srv/vault"
        full_path = vault_root / path

        if not full_path.exists():
            return f"Error: File not found: {path}"

        try:
            content = full_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            if len(lines) > max_lines:
                content = "\n".join(lines[:max_lines]) + f"\n\n... [{len(lines) - max_lines} more lines]"
            return content
        except Exception as e:
            return f"Error reading file: {str(e)}"


class TavilySearchTool(BaseTool):
    """Search for current clinical guidelines and medical information online using Tavily."""

    name: str = "TavilySearch"
    description: str = (
        "Search the web for current clinical guidelines, medical protocols, "
        "and healthcare best practices. Use this to find the latest evidence-based guidelines. "
        "Input should be a JSON string with keys: query (search string), "
        "topic (optional, e.g. 'clinical_guidelines', 'treatment_protocol'), "
        "max_results (default 5)."
    )

    def _run(self, query: str, topic: str = "clinical_guidelines", max_results: int = 5) -> str:
        """Search for clinical guidelines online.

        Args:
            query: Search query for clinical guidelines
            topic: Medical topic category
            max_results: Maximum number of results

        Returns:
            JSON string with search results
        """
        # Lazy import to avoid dependency if not used
        try:
            from crewai_tools import TavilySearchTool as CrewAITavilySearchTool
        except ImportError:
            return '{"error": "crewai_tools not installed. Install with: pip install crewai_tools"}'

        global _tavily_tool
        if _tavily_tool is None:
            _tavily_tool = CrewAITavilySearchTool()

        # Perform search via the underlying tool
        try:
            results = _tavily_tool._run(query=query, topic=topic, max_results=max_results)
            return results
        except Exception as e:
            return json.dumps({"error": str(e), "query": query})


class AgentBusTool(BaseTool):
    """Send messages to other agents via Redis pub/sub."""

    name: str = "AgentBus"
    description: str = (
        "Send a message to another agent or receive messages. "
        "Use to: request_info (ask another agent for information), "
        "provide_info (send results back), task_complete (notify completion). "
        "Format: send to='AgentName' action='research_request' data={...} "
        "Or recv timeout=30 to wait for a response."
    )

    def _run(
        self,
        action: str = "send",
        to: str = "",
        from_: str = "",
        data: str = "{}",
        timeout: int = 30,
        recv_agent: str = "CMedO",
    ) -> str:
        """Run the AgentBus tool.

        Args:
            action: 'send' or 'recv'
            to: Recipient agent name (for send)
            from_: Sender agent name (for send) — this is WHO IS CALLING (the sender)
            data: JSON payload (for send)
            timeout: Seconds to wait for recv
            recv_agent: Agent name to subscribe as for recv (the RECEIVER's channel)
        """
        # Lazy import to avoid circular dependencies
        from src.agent_bus import AgentBus

        bus = AgentBus()

        if action == "send":
            # 'from_' is the SENDER — who is calling this tool
            try:
                parsed = json.loads(data) if isinstance(data, str) and data.startswith("{") else {}
            except (json.JSONDecodeError, ValueError):
                parsed = {"raw": data}
            msg_id = bus.send(to=to, from_=from_, action=action, data=parsed)
            return f"Message sent: {msg_id}"
        elif action == "recv":
            # recv_agent is THIS agent — subscribe to its own channel
            bus = AgentBus()
            msg = bus.recv(agent_name=recv_agent, timeout=timeout)
            if msg:
                return json.dumps(msg, indent=2)
            return "No message received."
        return "Unknown action. Use send or recv."


class ClinicalGuidelines(Agent):
    """Clinical Guidelines Agent for Aestas Healthcare.

    This agent specializes in managing clinical guidelines, medical protocols,
    and healthcare best practices. It has deep knowledge of:
    - Hungarian healthcare guidelines and protocols
    - Swedish 1177 patient education model (1177.se)
    - Evidence-based medical guidelines
    - Medical research maps of content

    The agent can:
    - Search local vault for existing guidelines
    - Retrieve and summarize clinical documents
    - Search online for current guidelines via Tavily
    - Store new guidelines in the vault structure
    - Communicate with other C-suite agents via AgentBus
    """

    def __init__(self, tools: Optional[List[BaseTool]] = None):
        # Default tools if none provided
        if tools is None:
            tools = [
                VaultStorageTool(),
                VaultSearchTool(),
                VaultReadTool(),
                TavilySearchTool(),
                AgentBusTool(),
            ]

        super().__init__(
            role="Clinical Guidelines Specialist",
            goal=(
                "Provide accurate, evidence-based clinical guidelines and medical knowledge "
                "to support Aestas Healthcare's patient education portal. Search existing "
                "guidelines, retrieve relevant protocols, and maintain the guidelines vault "
                "with current best practices from Hungarian and international sources."
            ),
            backstory=(
                "You are a medical knowledge specialist with deep expertise in clinical guidelines, "
                "healthcare protocols, and evidence-based medicine. You have spent years curating "
                "medical knowledge bases and understand the nuances of Hungarian healthcare "
                "regulations and the Swedish 1177 patient education model. You are meticulous "
                "about accuracy and always cite sources. You believe that clear, accessible "
                "patient education is fundamental to improving healthcare outcomes. "
                "You work alongside the CMO to ensure all content meets clinical standards, "
                "collaborate with the CFO on resource allocation for medical content development, "
                "coordinate with the COO on operational guidelines, and support the CTO with "
                "technical requirements for the medical knowledge system."
            ),
            verbose=True,
            tools=tools,
            llm=_get_llm(),
        )


def get_clinical_guidelines(tools: Optional[List[BaseTool]] = None) -> ClinicalGuidelines:
    """Factory function to create the ClinicalGuidelines agent.

    Args:
        tools: Override tools list. Pass empty list [] when using ClinicalGuidelines as a
               hierarchical manager agent (CrewAI forbids manager agents having tools).

    Returns:
        ClinicalGuidelines agent instance
    """
    if tools is not None:
        # Create ClinicalGuidelines with custom tools
        class CMedOManager(ClinicalGuidelines):
            def __init__(self):
                super().__init__(tools=tools)

        return CMedOManager()
    return ClinicalGuidelines(tools=tools)
