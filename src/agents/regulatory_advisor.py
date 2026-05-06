"""RegulatoryAdvisor Agent — Hungarian Healthcare Regulatory Intelligence.

This agent monitors Hungarian healthcare regulations, provides compliance guidance,
and alerts on regulatory changes. It maintains a local database of Hungarian healthcare
laws and monitors official sources for updates.

Uses REGULATORY_PROMPT.md for focused Hungarian regulatory framework knowledge.

Vault path: /home/zoltan/srv/vault/Second Brain/raw/Aestas_CMedO/regulations/
Hungarian regulatory database: hungary/Hungarian_Healthcare_Legal_Risk_Framework.md
Monitoring sources: magyarkozlony.hu, neak.gov.hu, e-egeszsegugy.gov.hu, pharmindex-online.hu, mok.hu
"""

from crewai import Agent
from crewai.llm import LLM
from crewai.tools import BaseTool
from typing import Optional, ClassVar, Dict
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
# VAULT STORAGE TOOL
# =============================================================================

VAULT_ROOT = Path.home() / "srv" / "vault" / "Second Brain" / "raw"
VAULT_REGULATIONS_PATH = VAULT_ROOT / "Aestas_CMedO" / "regulations"
HUNGARIAN_DB_PATH = VAULT_REGULATIONS_PATH / "hungary" / "Hungarian_Healthcare_Legal_Risk_Framework.md"

# Regulatory Prompt path
REGULATORY_PROMPT_PATH = Path("/home/zoltan/srv/crewai/ai_council/src/prompts/REGULATORY_PROMPT.md")


def _load_regulatory_prompt() -> str:
    """Load the REGULATORY_PROMPT.md for domain knowledge."""
    if REGULATORY_PROMPT_PATH.exists():
        return REGULATORY_PROMPT_PATH.read_text(encoding="utf-8")
    return ""


class VaultStorageTool(BaseTool):
    """Saves regulatory documents and analyses to the vault folder structure.

    Documents are saved with YAML frontmatter containing metadata.
    Folder: VAULT_ROOT / Aestas_CMedO / regulations / {sub_folder} / {timestamp}_{title}.md
    """

    name: str = "RegulatoryVaultStorage"
    description: str = (
        "Saves regulatory documents, analyses, and compliance reports to the vault. "
        "Input should be a JSON string with keys: content (markdown), title (string), "
        "and optional metadata (dict with doc_type, tags, region)."
    )

    agent_folder: str = "Aestas_CMedO"
    sub_folder: str = "regulations"

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
            folder = VAULT_REGULATIONS_PATH / region / doc_type
        else:
            folder = VAULT_REGULATIONS_PATH / doc_type

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
agent: Aestas_CMedO
doc_type: {doc_type}
region: {region}
timestamp: {datetime.now().isoformat()}
tags: [{tags_str}]
---

"""
        path.write_text(frontmatter + content, encoding="utf-8")
        return f"Saved: {path.relative_to(VAULT_ROOT)}"


# =============================================================================
# TAVILY SEARCH TOOL
# =============================================================================

class TavilySearchTool(BaseTool):
    """Web search tool for monitoring Hungarian healthcare regulatory sources.

    Monitors: magyarkozlony.hu (Hungarian Gazette), neak.gov.hu (National Health Insurance),
    e-egeszsegugy.gov.hu (e-Health), pharmindex-online.hu (Pharma Index), mok.hu (Medical Chamber).
    """

    name: str = "TavilySearch"
    description: str = (
        "Search the web for Hungarian healthcare regulatory information. "
        "Use for monitoring official sources: magyarkozlony.hu, neak.gov.hu, "
        "e-egeszsegugy.gov.hu, pharmindex-online.hu, mok.hu. "
        "Input: search query string (e.g., 'egészségügyi törvény 2024' or 'healthcare regulation Hungary')."
    )

    def _run(self, query: str = "") -> str:
        """Search for regulatory information.

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
# REGULATORY DATABASE READER TOOL
# =============================================================================

class RegulatoryDatabaseTool(BaseTool):
    """Reads the Hungarian Healthcare Legal Risk Framework from the vault.

    This is the primary local database for Hungarian healthcare regulations.
    """

    name: str = "RegulatoryDatabaseReader"
    description: str = (
        "Reads the Hungarian Healthcare Legal Risk Framework database. "
        "Use this to answer questions about Hungarian healthcare laws, regulations, "
        "and compliance requirements. Input: search query or topic to look up."
    )

    def _run(self, query: str = "") -> str:
        """Search the regulatory database.

        Args:
            query: Topic or keyword to search for in the database

        Returns:
            Relevant sections from the Hungarian regulatory database
        """
        if not HUNGARIAN_DB_PATH.exists():
            return f'{{"error": "Regulatory database not found at {HUNGARIAN_DB_PATH}"}}'

        try:
            content = HUNGARIAN_DB_PATH.read_text(encoding="utf-8")

            if not query:
                return content[:10000]  # Return first 10k chars if no query

            # Simple keyword matching (could be enhanced with embeddings)
            query_lower = query.lower()
            lines = content.split("\n")
            relevant_lines = []

            for line in lines:
                if query_lower in line.lower():
                    relevant_lines.append(line)
                    # Add context (next 2 lines)
                    idx = lines.index(line)
                    for i in range(idx + 1, min(idx + 3, len(lines))):
                        if lines[i].strip():
                            relevant_lines.append(lines[i])

            if relevant_lines:
                return "\n".join(relevant_lines[:100])  # Limit output
            return "No relevant content found in database."

        except Exception as e:
            return f'{{"error": "{str(e)}"}}'


# =============================================================================
# REGULATORY SOURCE MONITOR TOOL
# =============================================================================

class RegulatorySourceMonitorTool(BaseTool):
    """Monitors Hungarian healthcare regulatory sources for updates.

    Sources: magyarkozlony.hu, neak.gov.hu, e-egeszsegugy.gov.hu, pharmindex-online.hu, mok.hu
    """

    name: str = "RegulatorySourceMonitor"
    description: str = (
        "Monitor Hungarian healthcare regulatory websites for updates. "
        "Sources: magyarkozlony.hu (Magyar Közlöny - Hungarian Gazette), "
        "neak.gov.hu (NEAK - National Health Insurance Fund), "
        "e-egeszsegugy.gov.hu (e-Health Hungary), "
        "pharmindex-online.hu (Pharma Index), "
        "mok.hu (Hungarian Medical Chamber). "
        "Input: source name or 'all' to check all sources."
    )

    SOURCES: ClassVar[Dict[str, str]] = {
        "magyarkozlony": "https://magyarkozlony.hu",
        "neak": "https://www.neak.gov.hu",
        "e-egeszsegugy": "https://e-egeszsegugy.gov.hu",
        "pharmindex": "https://pharmindex-online.hu",
        "mok": "https://www.mok.hu",
    }

    def _run(self, source: str = "all") -> str:
        """Check regulatory sources for updates.

        Args:
            source: Source name ('all', 'magyarkozlony', 'neak', 'e-egeszsegugy', 'pharmindex', 'mok')

        Returns:
            JSON with source URLs to check (actual scraping should be done separately)
        """
        if source == "all":
            return json.dumps({"sources": self.SOURCES}, indent=2)

        url = self.SOURCES.get(source.lower())
        if not url:
            return f'{{"error": "Unknown source: {source}. Available: {list(self.SOURCES.keys())}"}}'

        return json.dumps({"source": source, "url": url, "status": "ready_to_check"}, indent=2)


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
        from_: str = "RegulatoryAdvisor",
        data: str = "{}",
        timeout: int = 30,
        recv_agent: str = "RegulatoryAdvisor"
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
# REGULATORY ADVISOR AGENT
# =============================================================================

class RegulatoryAdvisor(Agent):
    """Regulatory Advisor agent for Hungarian Healthcare compliance.

    The RegulatoryAdvisor provides:
    - Compliance guidance for Hungarian healthcare regulations
    - Monitoring of regulatory changes from official sources
    - Risk assessment based on Hungarian healthcare law
    - Alerts on new regulations affecting healthcare businesses

    Tools:
    - VaultStorageTool: Save regulatory analyses to vault
    - TavilySearchTool: Search for regulatory information online
    - RegulatoryDatabaseTool: Query local Hungarian regulatory database
    - RegulatorySourceMonitorTool: Monitor official Hungarian regulatory sources
    - AgentBusTool: Communicate with other agents
    """

    def __init__(self):
        super().__init__(
            role="Regulatory Advisor (CMedO)",
            goal=(
                "Ensure Aestas Healthcare operates in full compliance with Hungarian "
                "healthcare regulations. Monitor regulatory changes, provide compliance "
                "guidance, assess legal risks, and alert the team to regulatory developments "
                "that may impact operations."
            ),
            backstory=(
                "You are a seasoned healthcare regulatory expert with deep knowledge of "
                "Hungarian healthcare law, EU healthcare directives, and medical device "
                "regulations. You have 15+ years of experience advising pharmaceutical "
                "companies, medical device manufacturers, and healthcare service providers "
                "on Hungarian regulatory compliance. You track every amendment to the "
                "Egészségügyi Törvény (Health Act), NEAK reimbursement regulations, and "
                "the Hungarian Medical Chamber's guidelines. You speak Hungarian natively "
                "and can navigate the complex landscape of magyarkozlony.hu, neak.gov.hu, "
                "and other official regulatory portals. You believe proactive compliance "
                "is cheaper than reactive penalties."
            ),
            verbose=_get_config().VERBOSE,
            tools=[
                VaultStorageTool(),
                TavilySearchTool(),
                RegulatoryDatabaseTool(),
                RegulatorySourceMonitorTool(),
                AgentBusTool(),
            ],
            llm=_get_llm(),
        )


def get_regulatory_advisor(tools: list = None) -> RegulatoryAdvisor:
    """Factory function to create the RegulatoryAdvisor agent.

    Args:
        tools: Override tools list. Pass empty list [] when using RegulatoryAdvisor as a
               hierarchical manager agent (CrewAI forbids manager agents having tools).

    Returns:
        RegulatoryAdvisor instance
    """
    if tools is not None:
        class RegulatoryAdvisorManager(RegulatoryAdvisor):
            def __init__(self):
                super().__init__()
                object.__setattr__(self, 'tools', tools)
        return RegulatoryAdvisorManager()
    return RegulatoryAdvisor()
