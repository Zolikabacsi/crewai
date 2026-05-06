"""PatientSafety Agent — Clinical safety officer for Aestas Healthcare.

This agent serves as a dedicated patient safety specialist for cross-border
continuity-of-care scenarios. It maintains expertise in:
- Incident review templates (critical event analysis, root cause analysis)
- Prescribing safety (drug interactions, contra-indications, cross-border Rx)
- Cross-border continuity-of-care checklists (EU healthcare directives, e-prescription)

Uses SAFETY_PROMPT.md for focused patient safety framework guidance.

The agent has deep knowledge of:
- EU patient safety frameworks and directives
- Hungarian and European healthcare regulations
- Medication safety standards (LASA, Look-Alike Sound-Alike)
- Cross-border healthcare (EHR portability, e-prescription across borders)
"""

from crewai import Agent
from crewai.llm import LLM
from crewai.tools import BaseTool
from pydantic import Field
from typing import Optional, List
from pathlib import Path
from datetime import datetime

import os

# Ensure environment is configured for custom endpoints
from ..config import Config

if Config.ANTHROPIC_AUTH_TOKEN:
    os.environ["ANTHROPIC_API_KEY"] = Config.ANTHROPIC_AUTH_TOKEN
if Config.ANTHROPIC_BASE_URL:
    os.environ["ANTHROPIC_BASE_URL"] = Config.ANTHROPIC_BASE_URL.rstrip("/v1")

# Vault path for Aestas Clinical Medical Officer - Safety
VAULT_SAFETY_PATH = Path("/home/zoltan/srv/vault/Second Brain/raw/Aestas_CMedO/safety")

# Safety Prompt path
SAFETY_PROMPT_PATH = Path("/home/zoltan/srv/crewai/ai_council/src/prompts/SAFETY_PROMPT.md")


def _load_safety_prompt() -> str:
    """Load the SAFETY_PROMPT.md for domain knowledge."""
    if SAFETY_PROMPT_PATH.exists():
        return SAFETY_PROMPT_PATH.read_text(encoding="utf-8")
    return ""


def get_llm():
    """Create LLM instance for PatientSafety agent with MiniMax-M2.7 model."""
    return LLM(
        provider="anthropic",
        model="MiniMax-M2.7",
        api_key=Config.ANTHROPIC_AUTH_TOKEN,
        base_url=Config.ANTHROPIC_BASE_URL.rstrip("/v1") if Config.ANTHROPIC_BASE_URL else "https://chat.ultimateai.org",
    )


# ----------------------------------------------------------------------
# Custom Tools
# ----------------------------------------------------------------------


class VaultStorageTool(BaseTool):
    """Saves patient safety documents to the vault folder structure.

    Saves documents to: VAULT_ROOT / Aestas_CMedO / safety / {timestamp}_{title}.md
    Where VAULT_ROOT = ~/srv/vault/Second Brain/raw

    Supports:
    - Incident review templates
    - Prescribing safety alerts
    - Cross-border continuity checklists
    """

    name: str = "VaultStorageTool"
    description: str = (
        "Saves patient safety documents to the vault folder structure. "
        "Use this to permanently store incident reviews, prescribing safety alerts, "
        "and continuity-of-care checklists. "
        "Input should be a JSON string with keys: content (markdown), title (string), "
        "doc_type (incident_review | prescribing_safety | continuity_care), "
        "and optional metadata (dict with tags, severity, jurisdiction)."
    )

    def _run(self, content: str, title: str, doc_type: str = "general",
             metadata: Optional[dict] = None) -> str:
        """Save content to vault safety folder.

        Args:
            content: The document content to save (markdown)
            title: Short descriptive title for the document
            doc_type: Document type (incident_review, prescribing_safety, continuity_care, general)
            metadata: Optional dict with keys: tags, severity, jurisdiction

        Returns:
            Path to saved file relative to vault root
        """
        folder = VAULT_SAFETY_PATH / doc_type
        folder.mkdir(parents=True, exist_ok=True)

        # Create slug for filename
        slug = title.lower().replace(" ", "_").replace("/", "-").replace("\\", "-")[:50]
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug}.md"
        path = folder / filename

        # Build tags string for frontmatter
        tags_list = metadata.get("tags", []) if metadata else []
        severity = metadata.get("severity", "") if metadata else ""
        jurisdiction = metadata.get("jurisdiction", "") if metadata else ""
        tags_str = ", ".join(tags_list) if tags_list else ""

        # Write with frontmatter header
        frontmatter = f"""---
title: {title}
agent: PatientSafety
doc_type: {doc_type}
timestamp: {datetime.now().isoformat()}
tags: [{tags_str}]
severity: {severity}
jurisdiction: {jurisdiction}
---

"""
        path.write_text(frontmatter + content, encoding="utf-8")
        return f"Saved: {path.relative_to(VAULT_SAFETY_PATH.parent.parent)}"


class TavilySearchTool(BaseTool):
    """Web search tool for patient safety information.

    Uses Tavily API to search for:
    - EU patient safety directives and guidelines
    - Cross-border healthcare regulations
    - Medication safety updates
    - Critical incident reporting standards
    """

    name: str = "TavilySearchTool"
    description: str = (
        "Search the web for patient safety information. "
        "Use to find: EU healthcare directives, prescribing safety guidelines, "
        "cross-border continuity-of-care protocols, incident review methodologies, "
        "and medication safety alerts. "
        "Input: search query string. Output: search results with URLs and summaries."
    )

    def _run(self, query: str = "") -> str:
        """Execute web search for patient safety information.

        Args:
            query: Search query string

        Returns:
            JSON string with search results
        """
        if not query:
            return '{"error": "No search query provided"}'

        try:
            from crewai_tools import TavilySearchTool as CrewTavilySearch
            tool = CrewTavilySearch()
            results = tool._run(query=query)
            return results
        except ImportError:
            return '{"error": "crewai_tools TavilySearchTool not installed"}'
        except Exception as e:
            return f'{{"error": "{str(e)}"}}'


class AgentBusTool(BaseTool):
    """Inter-agent communication via Redis pub/sub for patient safety.

    Allows the PatientSafety agent to:
    - Report safety incidents to compliance officers
    - Request medication info from pharmacy agents
    - Coordinate with cross-border care coordinators
    - Alert other agents to critical safety events
    """

    name: str = Field(default="AgentBusTool")
    description: str = (
        "Send a message to another agent or receive messages via the agent bus. "
        "Use for: reporting safety incidents (to ComplianceOfficer, CMO), "
        "requesting medication information (from PharmacyAgent), "
        "coordinating cross-border care (with CareCoordinator), "
        "alerting to critical safety events. "
        "Format: send to='AgentName' action='send' data={...} "
        "Or recv timeout=30 to wait for a response."
    )

    def _run(self, action: str = "send", to: str = "", from_: str = "PatientSafety",
             data: str = "{}", timeout: int = 30, recv_agent: str = "PatientSafety") -> str:
        """Run the AgentBus tool.

        Args:
            action: 'send' or 'recv'
            to: Recipient agent name (for send)
            from_: Sender agent name (for send)
            data: JSON payload (for send)
            timeout: Seconds to wait for recv
            recv_agent: Agent name to subscribe as for recv

        Returns:
            Status message or received message JSON
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
            msg = bus.recv(agent_name=recv_agent, timeout=timeout)
            if msg:
                import json
                return json.dumps(msg, indent=2)
            return "No message received."
        return "Unknown action. Use send or recv."


import json


# ----------------------------------------------------------------------
# PatientSafety Agent
# ----------------------------------------------------------------------


class PatientSafety(Agent):
    """Patient Safety Agent — Clinical safety specialist for cross-border care.

    The PatientSafety agent is a dedicated specialist for patient safety in
    cross-border continuity-of-care scenarios within Aestas Healthcare.

    CORE EXPERTISE:
    - Incident Review Templates: Root Cause Analysis (RCA), Failure Mode and
      Effects Analysis (FMEA), Serious Incident (SI) reviews, near-miss reporting
    - Prescribing Safety: LASA medications, drug-drug interactions, contra-indications,
      dose adjustments for special populations, cross-border prescription validity
    - Cross-Border Continuity-of-Care: EU healthcare directives, e-prescription
      portability (ePrescription Exchange), EHR summary standards, patient ID
      matching across systems

    REGULATORY FRAMEWORK:
    - EU Directive 2011/24/EU on patients' rights in cross-border healthcare
    - EU eHealth Network guidelines on ePrescription cross-border exchange
    - Hungarian healthcare regulations (EÜAk, 1997. CLIV tv.)
    - WHO Medication Safety Standards
    - ISMP (Institute for Safe Medication Practices) guidelines

    BEHAVIOR:
    - Vigilant: Always checks for safety implications before approving any action
    - Documented: All safety decisions logged with reasoning
    - Proactive: Anticipates risks in cross-border scenarios
    - Collaborative: Works with PharmacyAgent, ComplianceOfficer, CareCoordinator
    """

    def __init__(self):
        super().__init__(
            role="Patient Safety Officer",
            goal=(
                "Ensure patient safety in all cross-border continuity-of-care scenarios. "
                "Develop and maintain incident review templates, prescribing safety protocols, "
                "and cross-border care checklists. Identify risks proactively, document all "
                "safety-critical decisions, and coordinate with other agents to prevent "
                "adverse events in Hungarian and European healthcare contexts."
            ),
            backstory=(
                "You are a board-certified patient safety officer with 15+ years of experience "
                "in clinical risk management and medication safety. You hold credentials in "
                "root cause analysis, failure mode effects analysis, and healthcare quality "
                "improvement. You have implemented safety systems at major hospital networks "
                "across the EU and contributed to WHO medication safety guidelines. "
                "Your expertise spans EU cross-border healthcare directives, e-prescription "
                "standards, and EHR interoperability frameworks. You speak Hungarian and "
                "English fluently, with working knowledge of German and Romanian for "
                "cross-border care coordination. You believe every adverse event is "
                "preventable through systematic analysis and proactive risk assessment."
            ),
            verbose=Config.VERBOSE,
            tools=[
                VaultStorageTool(),
                TavilySearchTool(),
                AgentBusTool(),
            ],
            llm=get_llm(),
        )


def get_patient_safety(tools: list = None) -> PatientSafety:
    """Factory function to create the PatientSafety agent.

    Args:
        tools: Override tools list. Pass empty list [] when using PatientSafety as a
               hierarchical manager agent (CrewAI forbids manager agents having tools).

    Returns:
        PatientSafety agent instance
    """
    if tools is not None:
        # Create PatientSafety with custom tools (for manager use, pass tools=[])
        class PatientSafetyManager(PatientSafety):
            def __init__(self):
                super().__init__()
                # Override tools with provided list
                object.__setattr__(self, 'tools', tools)

        return PatientSafetyManager()
    return PatientSafety()
