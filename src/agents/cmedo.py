"""CMedO Agent — Chief Medical & Ethics Officer for Aestas Healthcare.

This agent serves as the CMedO (Chief Medical & Ethics Officer) leader for Aestas Healthcare,
coordinating medical, clinical, patient safety, regulatory, and compliance operations.

LEADER MODE: Coordinates three specialized sub-agents:
- RegulatoryAdvisor: Hungarian healthcare regulatory intelligence and compliance
- ClinicalGuidelines: Medical knowledge management and clinical protocol adherence
- PatientSafety: Patient safety, incident review, and cross-border continuity-of-care

OPERATIONAL MODE: Uses Claude Code subprocess for deep medical research, evidence synthesis,
and clinical document generation. Uses CMEDO_TASK_PROMPT.md (trimmed ~80-line version)
instead of the full 520-line CMEDO_PARTNER_PROMPT.md. Saves all outputs to vault/Aestas_CMedO/
with YAML frontmatter.

The agent has veto authority on unsafe or non-compliant proposals and routes complex
domain questions to sub-agents before synthesizing unified CMEDO PARTNER ANALYSIS responses.
"""

from crewai import Agent
from crewai.llm import LLM
from crewai.tools import BaseTool
from crewai_tools import DirectoryReadTool, FileReadTool, TavilySearchTool
from ..config import Config
from pathlib import Path
from datetime import datetime
from typing import Optional, List, ClassVar

import os

# ── Vault context helper ──────────────────────────────────────────────────────
def _get_vault_context(question: str, sections: list[str] | None = None) -> str:
    """Fetch relevant vault context before calling sub-agents."""
    try:
        from src.tools.second_brain_tool import SecondBrainKnowledgeTool
        tool = SecondBrainKnowledgeTool()
        ctx = tool._run(query=question, sections=sections)
        if ctx and "not found" not in ctx.lower()[:100] and "No results" not in ctx:
            return f"\n\n## Relevant Context from Second Brain Vault\n{ctx}\n"
    except Exception:
        pass
    return ""
import re
import json
import subprocess

# Ensure environment is configured for custom endpoints
if Config.ANTHROPIC_AUTH_TOKEN:
    os.environ["ANTHROPIC_API_KEY"] = Config.ANTHROPIC_AUTH_TOKEN
if Config.ANTHROPIC_BASE_URL:
    os.environ["ANTHROPIC_BASE_URL"] = Config.ANTHROPIC_BASE_URL.rstrip("/v1")

# Vault path for Aestas CMedO content
VAULT_CMEDO_PATH = Path("/home/zoltan/srv/vault/Second Brain/raw/Aestas_CMedO")

# CMEDO Task Prompt path (trimmed version for run_cmedo_task)
CMEDO_TASK_PROMPT_PATH = Path("/home/zoltan/srv/crewai/ai_council/src/prompts/CMEDO_TASK_PROMPT.md")

# Sub-agent registry for routing
SUB_AGENTS = {
    "RegulatoryAdvisor": "regulatory_advisor",
    "ClinicalGuidelines": "clinical_guidelines",
    "PatientSafety": "patient_safety",
}

# Domain prompt paths
REGULATORY_PROMPT_PATH = Path("/home/zoltan/srv/crewai/ai_council/src/prompts/REGULATORY_PROMPT.md")
CLINICAL_PROMPT_PATH = Path("/home/zoltan/srv/crewai/ai_council/src/prompts/CLINICAL_PROMPT.md")
SAFETY_PROMPT_PATH = Path("/home/zoltan/srv/crewai/ai_council/src/prompts/SAFETY_PROMPT.md")


def _load_prompt(path: Path) -> str:
    """Load a domain prompt file."""
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _classify_question(question: str) -> dict:
    """Classify which sub-agents are needed for this question.

    Returns dict with boolean flags: needs_regulatory, needs_clinical, needs_safety
    """
    q = question.lower()

    regulatory_kw = [
        "regulation", "regulatory", "compliance", "law", "hungarian", "gdpr",
        "hipaa", "approval", "license", "certification", "legal", "policy",
        "naeh", "neak", "eeszt", "mok", "data protection", "privacy",
        "consent", "transfer", "cross-border", "telemedicine decree",
        "contract", "reimbursement", "nEAK", "eüak",
    ]
    clinical_kw = [
        "guideline", "clinical", "medical", "treatment", "protocol",
        "diagnosis", "evidence", "therapy", "medication", "drug",
        "prescribe", "patient education", "1177", "ema", "who",
        "health authority", "ndvh", "nngyk", "orvosi", "gyógyszer",
    ]
    safety_kw = [
        "safety", "incident", "risk", "harm", "patient", "adverse",
        "death", "injury", "complication", "breach", "continuity",
        "prescribing", "lasa", "interaction", "contraindication",
        "side effect", "allergy", "elderly", "pediatric", " dosing",
    ]

    needs_regulatory = any(kw in q for kw in regulatory_kw)
    needs_clinical = any(kw in q for kw in clinical_kw)
    needs_safety = any(kw in q for kw in safety_kw)

    # If no specific routing, default to clinical (most common for content review)
    if not needs_regulatory and not needs_clinical and not needs_safety:
        needs_clinical = True

    return {
        "needs_regulatory": needs_regulatory,
        "needs_clinical": needs_clinical,
        "needs_safety": needs_safety,
    }


def get_llm():
    """Create LLM instance for CMedO agent with MiniMax-M2.7 model."""
    return LLM(
        provider="anthropic",
        model="MiniMax-M2.7",
        api_key=Config.ANTHROPIC_AUTH_TOKEN,
        base_url=Config.ANTHROPIC_BASE_URL.rstrip("/v1") if Config.ANTHROPIC_BASE_URL else "https://chat.ultimateai.org",
    )


def _load_cmedo_task_prompt() -> str:
    """Load the CMEDO_TASK_PROMPT.md as the operational backbone for task execution."""
    if CMEDO_TASK_PROMPT_PATH.exists():
        return CMEDO_TASK_PROMPT_PATH.read_text(encoding="utf-8")
    return ""


# =============================================================================
# CUSTOM TOOLS
# =============================================================================


class VaultStorageTool(BaseTool):
    """Saves CMedO documents to the vault folder structure with YAML frontmatter.

    Saves documents to: VAULT_CMEDO_PATH / {category} / {timestamp}_{slug}.md

    Categories: clinical_reviews, guidelines, regulations, safety, analyses
    """

    name: str = "VaultStorageTool"
    description: str = (
        "Saves CMedO documents to the vault folder structure with YAML frontmatter. "
        "Input should be a JSON string with keys: content (markdown), title (string), "
        "category (one of: clinical_reviews, guidelines, regulations, safety, analyses), "
        "and optional metadata (dict with tags, doc_type, region, severity)."
    )
    category: str = "analyses"

    def _run(self, content: str, title: str, category: str = "analyses",
             metadata: Optional[dict] = None) -> str:
        """Save content to vault CMedO folder with YAML frontmatter.

        Args:
            content: The document content to save (markdown)
            title: Short descriptive title for the document
            category: Document category (clinical_reviews, guidelines, regulations, safety, analyses)
            metadata: Optional dict with keys: tags, doc_type, region, severity

        Returns:
            Path where document was saved relative to vault root
        """
        folder = VAULT_CMEDO_PATH / category
        folder.mkdir(parents=True, exist_ok=True)

        # Create slug for filename
        slug = title.lower().replace(" ", "_").replace("/", "-").replace("\\", "-")[:50]
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug}.md"
        path = folder / filename

        # Extract metadata
        tags_list = metadata.get("tags", []) if metadata else []
        doc_type = metadata.get("doc_type", category) if metadata else category
        region = metadata.get("region", "general") if metadata else "general"
        severity = metadata.get("severity", "") if metadata else ""
        tags_str = ", ".join(tags_list) if tags_list else ""

        # Write with YAML frontmatter
        frontmatter = f"""---
title: {title}
agent: Aestas_CMedO
doc_type: {doc_type}
category: {category}
region: {region}
severity: {severity}
timestamp: {datetime.now().isoformat()}
tags: [{tags_str}]
---

"""
        path.write_text(frontmatter + content, encoding="utf-8")
        return f"Saved: {path.relative_to(VAULT_CMEDO_PATH.parent.parent)}"


class ClaudeCodeTool(BaseTool):
    """Execute Claude Code CLI for deep medical research and document synthesis.

    This tool wraps the Claude Code CLI (claude) to perform:
    - Deep medical literature searches and evidence synthesis
    - Clinical document generation with proper citations
    - Medical guideline analysis and comparison
    - Regulatory document drafting and review

    Results are automatically saved to vault/Aestas_CMedO/ with frontmatter.
    """

    name: str = "ClaudeCodeTool"
    description: str = (
        "Execute Claude Code CLI for deep medical research and document synthesis. "
        "Use for: medical literature searches, clinical document generation, "
        "guideline analysis, regulatory document drafting. "
        "Input should be a JSON string with keys: prompt (task description), "
        "task_type (one of: research, clinical_doc, guideline_analysis, regulatory_draft, safety_review), "
        "output_category (vault category to save to), and optional metadata (dict with tags, region)."
    )

    def _run(self, prompt: str, task_type: str = "research",
             output_category: str = "analyses",
             metadata: Optional[dict] = None) -> str:
        """Execute Claude Code CLI for the given medical task.

        Args:
            prompt: The task description/prompt for Claude Code
            task_type: Type of task (research, clinical_doc, guideline_analysis, regulatory_draft, safety_review)
            output_category: Vault category to save output
            metadata: Optional dict with tags, region for frontmatter

        Returns:
            Claude Code output or error message
        """
        # Build the full prompt with context
        cmedo_context = _load_cmedo_task_prompt()
        full_prompt = f"""You are acting as the CMedO (Chief Medical & Ethics Officer) for Aestas Healthcare.

Use the following CMedO Task prompt as your operational backbone:

---
{cmedo_context[:8000]}  # Truncate if needed
---

TASK: {prompt}

Task Type: {task_type}

Output Format: Return your response as a well-structured medical/clinical document with:
- Clear section headers
- Evidence-based reasoning
- Regulatory compliance notes where applicable
- Explicit safety assessments
- Recommended actions with优先级

Save the output as a markdown document that will be stored in vault/Aestas_CMedO/{output_category}/"""

        try:
            # Execute Claude Code CLI
            result = subprocess.run(
                ["claude", "--print", full_prompt],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for complex medical research
                env={**os.environ, "ANTHROPIC_API_KEY": Config.ANTHROPIC_AUTH_TOKEN or ""}
            )

            if result.returncode != 0:
                return f"Claude Code error (exit {result.returncode}): {result.stderr}"

            output = result.stdout

            # Auto-save to vault if output is substantial
            if len(output) > 500:
                # Extract title from output or generate one
                first_line = output.split("\n")[0] if output else "Claude_Code_Output"
                title = first_line.strip("# ").strip()[:60] if first_line.startswith("#") else f"{task_type}_{datetime.now().strftime('%Y%m%d')}"

                storage_tool = VaultStorageTool()
                storage_tool.category = output_category
                save_result = storage_tool._run(
                    content=output,
                    title=title,
                    category=output_category,
                    metadata=metadata
                )
                return f"{output}\n\n[Auto-saved to vault: {save_result}]"

            return output

        except subprocess.TimeoutExpired:
            return '{"error": "Claude Code timed out after 5 minutes"}'
        except FileNotFoundError:
            return '{"error": "Claude Code CLI not found. Ensure claude is installed and in PATH."}'
        except Exception as e:
            return f'{{"error": "{str(e)}"}}'


class AgentBusTool(BaseTool):
    """Route tasks to specialized sub-agents (RegulatoryAdvisor, ClinicalGuidelines, PatientSafety).

    This tool allows the CMedO leader to delegate tasks to its specialized sub-agents
    and receive their responses. Messages are routed via Redis pub/sub.
    """

    name: str = "AgentBus"
    description: str = (
        "Route tasks to specialized CMedO sub-agents: RegulatoryAdvisor, ClinicalGuidelines, "
        "PatientSafety. Use to: delegate regulatory research, request clinical guideline reviews, "
        "initiate patient safety assessments, coordinate multi-agent medical analyses. "
        "Format: send to='SubAgentName' action='send' data={{'task': 'description', 'task_type': 'type'}} "
        "Or recv timeout=30 to wait for a response."
    )

    def _run(self, action: str = "send", to: str = "", from_: str = "CMedO",
             data: str = "{}", timeout: int = 30, recv_agent: str = "CMedO") -> str:
        """Route task to or receive from sub-agent.

        Args:
            action: 'send' or 'recv'
            to: Recipient sub-agent name (RegulatoryAdvisor, ClinicalGuidelines, PatientSafety)
            from_: Sender agent name
            data: JSON payload with task description
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

            # Validate sub-agent name
            if to not in SUB_AGENTS:
                return f'{{"error": "Unknown sub-agent: {to}. Valid: {list(SUB_AGENTS.keys())}"}}'

            msg_id = bus.send(to=to, from_=from_, action=action, data=parsed)
            return f"Task routed to {to}: {msg_id}"

        elif action == "recv":
            msg = bus.recv(agent_name=recv_agent, timeout=timeout)
            if msg:
                return json.dumps(msg, indent=2)
            return "No message received."
        return "Unknown action. Use send or recv."


class RouteToSubAgentTool(BaseTool):
    """High-level task routing tool for CMedO leader coordination.

    This tool provides a simpler interface for routing common CMedO tasks
    to the appropriate sub-agent based on task characteristics.
    """

    name: str = "RouteToSubAgent"
    description: str = (
        "Route a medical/clinical task to the appropriate CMedO sub-agent based on task content. "
        "Analyzes the task and routes to: RegulatoryAdvisor (for regulatory/compliance questions), "
        "ClinicalGuidelines (for medical knowledge/guideline questions), "
        "PatientSafety (for safety/incident/risk questions). "
        "Input should be a JSON string with keys: task (string), priority (normal|high|critical), "
        "context (optional dict with additional context)."
    )

    TASK_ROUTING: ClassVar[dict] = {
        "regulatory": ["regulation", "compliance", "law", "hungarian", "gdpr", "hipaa",
                       "approval", "license", "certification", "legal", "policy"],
        "clinical": ["guideline", "clinical", "medical", "treatment", "protocol",
                     "diagnosis", "evidence", "research", "therapy", "medication"],
        "safety": ["safety", "incident", "risk", "harm", "patient", "adverse", "death",
                   "injury", "complication", "breach", "continuity", "prescribing"],
    }

    def _run(self, task: str, priority: str = "normal",
             context: Optional[dict] = None) -> str:
        """Analyze task and route to appropriate sub-agent.

        Args:
            task: Task description string
            priority: Task priority (normal, high, critical)
            context: Optional additional context

        Returns:
            Routing decision with sub-agent assignment
        """
        task_lower = task.lower()
        context = context or {}

        # Score each sub-agent based on task keywords
        scores = {"RegulatoryAdvisor": 0, "ClinicalGuidelines": 0, "PatientSafety": 0}

        for keyword in self.TASK_ROUTING["regulatory"]:
            if keyword in task_lower:
                scores["RegulatoryAdvisor"] += 2
        for keyword in self.TASK_ROUTING["clinical"]:
            if keyword in task_lower:
                scores["ClinicalGuidelines"] += 2
        for keyword in self.TASK_ROUTING["safety"]:
            if keyword in task_lower:
                scores["PatientSafety"] += 2

        # Also check for explicit mentions
        if "regulatory" in task_lower or "regulation" in task_lower:
            scores["RegulatoryAdvisor"] += 5
        if "clinical" in task_lower or "guideline" in task_lower:
            scores["ClinicalGuidelines"] += 5
        if "safety" in task_lower or "patient safety" in task_lower:
            scores["PatientSafety"] += 5

        # Find highest scoring agent
        max_score = max(scores.values())
        if max_score == 0:
            # Default routing based on keywords
            scores["ClinicalGuidelines"] = 1

        routed_agent = max(scores, key=scores.get)

        # Build task payload
        payload = {
            "task": task,
            "priority": priority,
            "context": context,
            "routed_by": "CMedO",
            "timestamp": datetime.now().isoformat(),
        }

        # Use AgentBus to send to sub-agent
        from src.agent_bus import AgentBus
        bus = AgentBus()
        msg_id = bus.send(to=routed_agent, from_="CMedO", action="send", data=payload)

        return json.dumps({
            "task": task,
            "routed_to": routed_agent,
            "message_id": msg_id,
            "priority": priority,
            "scores": scores,
            "status": "routed"
        }, indent=2)


# =============================================================================
# CMEDO AGENT
# =============================================================================


class CMedO(Agent):
    """Chief Medical & Ethics Officer agent — leader of medical/clinical operations.

    The CMedO leads Aestas Healthcare's medical, clinical, patient safety, and regulatory
    compliance operations through coordinated sub-agent teams.

    LEADER CAPABILITIES:
    - Routes tasks to RegulatoryAdvisor, ClinicalGuidelines, and PatientSafety sub-agents
    - Synthesizes multi-agent analyses into unified medical recommendations
    - Exercises veto authority on unsafe or non-compliant proposals
    - Maintains vault-based documentation of all medical decisions

    SUB-AGENT COORDINATION:
    - RegulatoryAdvisor: Hungarian healthcare regulatory intelligence
    - ClinicalGuidelines: Medical knowledge and clinical protocol management
    - PatientSafety: Patient safety, incident review, cross-border continuity-of-care

    TOOLS:
    - VaultStorageTool: Save medical documents to vault with YAML frontmatter
    - ClaudeCodeTool: Deep medical research via Claude Code CLI
    - AgentBusTool: Route tasks to sub-agents
    - RouteToSubAgentTool: Intelligent task routing based on content analysis
    - TavilySearchTool: Web search for medical/regulatory information
    - DirectoryReadTool / FileReadTool: Access vault and local files
    """

    def __init__(self):
        super().__init__(
            role="Chief Medical & Ethics Officer (CMedO)",
            goal=(
                "Ensure safe, evidence-based, compliant medical and clinical operations for "
                "Aestas Healthcare. Lead RegulatoryAdvisor, ClinicalGuidelines, and PatientSafety "
                "sub-agents to provide comprehensive medical oversight. Exercise veto authority "
                "on proposals that are non-compliant, medically unsafe, or inadequately governed. "
                "Maintain all medical decisions with vault-based documentation and YAML frontmatter."
            ),
            backstory=(
                "You are a seasoned Chief Medical & Ethics Officer with 20+ years of experience "
                "in healthcare leadership, having served as CMO at major hospital networks and "
                "health-tech companies. You hold board-level responsibility for patient safety, "
                "medical ethics, and regulatory compliance at Aestas Healthcare. Your expertise "
                "spans Hungarian and EU healthcare regulations, clinical guideline development, "
                "patient safety systems, and medical governance. You speak Hungarian natively "
                "and navigate EU/GDPR healthcare requirements with precision. You have veto rights "
                "over any proposal that threatens patient safety, regulatory compliance, or "
                "ethical standards — and you use them without hesitation. You coordinate three "
                "specialized sub-agents: RegulatoryAdvisor for Hungarian compliance, "
                "ClinicalGuidelines for medical knowledge, and PatientSafety for clinical risk "
                "management. You believe that excellent healthcare is built on systematic "
                "safety culture, evidence-based medicine, and proactive regulatory intelligence. "
                "You have live access to the Aestas Second Brain vault for domain context."
            ),
            verbose=Config.VERBOSE,
            tools=[
                VaultStorageTool(),
                ClaudeCodeTool(),
                AgentBusTool(),
                RouteToSubAgentTool(),
                DirectoryReadTool(),
                FileReadTool(),
                TavilySearchTool(),
                SecondBrainKnowledgeTool(),
            ],
            llm=get_llm(),
        )
        from src.tools.second_brain_tool import SecondBrainKnowledgeTool
        self.tools.append(SecondBrainKnowledgeTool())


def get_cmedo(tools: list = None) -> CMedO:
    """Factory function to create the CMedO agent.

    Args:
        tools: Override tools list. Pass empty list [] when using CMedO as a
               hierarchical manager agent (CrewAI forbids manager agents having tools).

    Returns:
        CMedO agent instance
    """
    if tools is not None:
        class CMedOManager(CMedO):
            def __init__(self):
                super().__init__()
                object.__setattr__(self, 'tools', tools)

        return CMedOManager()
    return CMedO()


def get_cmedo_agents() -> dict:
    """Factory function to create all CMedO agents including sub-agents.

    Returns:
        Dict with keys: cmedo (leader), regulatory_advisor, clinical_guidelines, patient_safety
    """
    # Import sub-agents
    from .regulatory_advisor import get_regulatory_advisor
    from .clinical_guidelines import get_clinical_guidelines
    from .patient_safety import get_patient_safety

    return {
        "cmedo": get_cmedo(),  # Leader with tools
        "regulatory_advisor": get_regulatory_advisor(),  # Sub-agent
        "clinical_guidelines": get_clinical_guidelines(),  # Sub-agent
        "patient_safety": get_patient_safety(),  # Sub-agent
    }


def _call_sub_agent(agent_name: str, prompt_template: str, question: str, context: str) -> str:
    """Call a sub-agent via Claude Code subprocess with domain-specific prompt.

    Args:
        agent_name: Name of the sub-agent (RegulatoryAdvisor, ClinicalGuidelines, PatientSafety)
        prompt_template: The domain-specific prompt for this sub-agent
        question: The specific question to answer
        context: Additional context about Aestas

    Returns:
        The sub-agent's response text (may be JSON or plain text)
    """
    claude_bin = Path.home() / ".local" / "bin" / "claude"

    # Pre-fetch relevant vault context
    vault_ctx = _get_vault_context(question, sections=["CMedO", "CFO"])

    prompt = f"""You are acting as the {agent_name} for Aestas Healthcare.

Use the following domain knowledge as your expert framework:

---
{prompt_template[:8000]}
---

QUESTION: {question}

CONTEXT: {context if context else "No additional context."}

{vault_ctx}INSTRUCTION: Answer the question using your domain expertise. Structure your response clearly with:
1. Direct answer
2. Supporting evidence or rationale
3. Key concerns or caveats
4. Recommended actions (if applicable)

Return your response as a well-structured text analysis."""

    try:
        env = {
            "ANTHROPIC_API_KEY": Config.ANTHROPIC_AUTH_TOKEN or "",
            "ANTHROPIC_BASE_URL": "https://chat.ultimateai.org",
        }
        result = subprocess.run(
            [str(claude_bin), "-p",
                prompt,  # positional arg (not stdin)
                "--model", "MiniMax-M2.7",
                "--output-format", "json",
                "--bare",  # non-interactive mode (no TTY required)
            ],
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ, **env},
        )

        if result.returncode != 0:
            return f"[{agent_name} error: Claude Code exit {result.returncode}]"

        raw = json.loads(result.stdout.strip())
        text = raw.get("result", raw.get("content", ""))
        return re.sub(r"\`\`\`(?:json)?\s*", "", text.strip()).strip()

    except subprocess.TimeoutExpired:
        return f"[{agent_name} timed out after 180s]"
    except json.JSONDecodeError:
        return f"[{agent_name} JSON parse error]"
    except Exception as e:
        return f"[{agent_name} error: {e}]"


def _synthesize_analysis(question: str, context: str,
                          regulatory_response: str,
                          clinical_response: str,
                          safety_response: str) -> dict:
    """Synthesize sub-agent responses into CMedO 10-field PARTNER ANALYSIS.

    Uses Claude Code for final synthesis.
    """
    claude_bin = Path.home() / ".local" / "bin" / "claude"

    synthesis_prompt = f"""You are the CMedO (Chief Medical & Ethics Officer) for Aestas Healthcare.
You have received analysis from three specialized sub-agents. Synthesize their findings into a unified CMedO PARTNER ANALYSIS.

---
CMEDO TASK PROMPT:
{_load_cmedo_task_prompt()}
---

QUESTION UNDER ANALYSIS: {question}

CONTEXT: {context if context else "No additional context."}

---
SUB-AGENT RESPONSES:

[REGULATORY ADVISOR]:
{regulatory_response}

[CLINICAL GUIDELINES]:
{clinical_response}

[PATIENT SAFETY]:
{safety_response}
---

INSTRUCTION: Synthesize the above sub-agent responses into a unified CMedO PARTNER ANALYSIS.

OUTPUT FORMAT: Return ONLY a JSON object with these exact fields (no text outside the JSON):
{{
  "bottom_line": "2-3 sentence executive summary",
  "diagnosis": "Clinical/regulatory diagnosis or assessment",
  "risk_level": "low|medium|high|critical",
  "recommendation": "Clear, actionable guidance",
  "medical_view": "Medical/clinical perspective and evidence",
  "gdpr_hipaa_view": "GDPR/HIPAA compliance perspective",
  "country_view": "Hungarian/EU regulatory perspective",
  "implementation": "Ordered implementation steps",
  "escalations": "Required escalations (ethics board, regulatory bodies, etc.)",
  "veto": "yes|no with rationale"
}}

Return ONLY the JSON object. Do not include markdown fences or any text outside the JSON."""

    try:
        env = {
            "ANTHROPIC_API_KEY": Config.ANTHROPIC_AUTH_TOKEN or "",
            "ANTHROPIC_BASE_URL": "https://chat.ultimateai.org",
        }
        result = subprocess.run(
            [str(claude_bin), "-p",
                synthesis_prompt,  # positional arg (not stdin)
                "--model", "MiniMax-M2.7",
                "--output-format", "json",
                "--bare",  # non-interactive mode (no TTY required)
            ],
            capture_output=True,
            text=True,
            timeout=240,
            env={**os.environ, **env},
        )

        if result.returncode != 0:
            return {
                "error": f"Synthesis Claude Code error (exit {result.returncode}): {result.stderr}",
                "vault_path": None,
            }

        raw = json.loads(result.stdout.strip())
        text = raw.get("result", raw.get("content", ""))
        text = re.sub(r"\`\`\`(?:json)?\s*", "", text.strip()).strip()
        text = text.rstrip("`")
        data = json.loads(text) if isinstance(text, str) else text

        required_keys = [
            "bottom_line", "diagnosis", "risk_level", "recommendation",
            "medical_view", "gdpr_hipaa_view", "country_view",
            "implementation", "escalations", "veto"
        ]
        for key in required_keys:
            if key not in data:
                data[key] = ""

        return data

    except subprocess.TimeoutExpired:
        return {"error": "Synthesis timed out after 240s", "vault_path": None}
    except json.JSONDecodeError as e:
        return {"error": f"Synthesis JSON parse error: {e}", "vault_path": None}
    except Exception as e:
        return {"error": f"Synthesis error: {e}", "vault_path": None}


def run_cmedo_task(question: str, context: str = "") -> dict:
    """Run a CMedO analysis task with proper sub-agent routing.

    This is the main entry point for CMedO operational tasks. It:
    1. Classifies the question to determine which sub-agents are needed
    2. Calls each relevant sub-agent via Claude Code with domain-specific prompts
    3. Collects sub-agent responses
    4. Synthesizes into the 10-field CMedO PARTNER ANALYSIS structure
    5. Saves to vault and returns the structured dict

    Args:
        question: The medical/clinical/regulatory question to analyze
        context: Additional context about Aestas, jurisdiction, etc.

    Returns:
        dict with keys: bottom_line, diagnosis, risk_level, recommendation,
                        medical_view, gdpr_hipaa_view, country_view,
                        implementation, escalations, veto, vault_path
    """
    # 1. Classify which sub-agents are needed
    routing = _classify_question(question)

    # 2. Load domain prompts
    regulatory_prompt = _load_prompt(REGULATORY_PROMPT_PATH)
    clinical_prompt = _load_prompt(CLINICAL_PROMPT_PATH)
    safety_prompt = _load_prompt(SAFETY_PROMPT_PATH)

    # 3. Call each relevant sub-agent in parallel via Claude Code
    regulatory_response = ""
    clinical_response = ""
    safety_response = ""

    if routing["needs_regulatory"]:
        regulatory_response = _call_sub_agent(
            "RegulatoryAdvisor", regulatory_prompt, question, context
        )

    if routing["needs_clinical"]:
        clinical_response = _call_sub_agent(
            "ClinicalGuidelines", clinical_prompt, question, context
        )

    if routing["needs_safety"]:
        safety_response = _call_sub_agent(
            "PatientSafety", safety_prompt, question, context
        )

    # 4. Synthesize into 10-field structure
    result = _synthesize_analysis(
        question, context,
        regulatory_response, clinical_response, safety_response
    )

    # 5. Save to vault if synthesis succeeded
    if "error" not in result:
        vault_dir = VAULT_CMEDO_PATH / "clinical_reviews"
        vault_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = question.lower().replace(" ", "_").replace("/", "-").replace("\\", "-")[:50]
        filename = f"{timestamp}_{slug}.md"
        vault_path = vault_dir / filename

        frontmatter = f"""---
title: "{question[:80]}"
type: clinical_review
created: {datetime.now().isoformat()}
tags: [cmedo, aestas]
risk_level: {result.get("risk_level", "unknown")}
routing: {{
  regulatory: {routing["needs_regulatory"]},
  clinical: {routing["needs_clinical"]},
  safety: {routing["needs_safety"]}
}}
---

# CMedO Partner Analysis

## Question
{question}

## Context
{context if context else "No additional context provided."}

## Sub-Agent Routing
- RegulatoryAdvisor: {'used' if routing['needs_regulatory'] else 'not needed'}
- ClinicalGuidelines: {'used' if routing['needs_clinical'] else 'not needed'}
- PatientSafety: {'used' if routing['needs_safety'] else 'not needed'}

## Sub-Agent Responses

### RegulatoryAdvisor
{regulatory_response or "[Not routed to regulatory]"}

### ClinicalGuidelines
{clinical_response or "[Not routed to clinical]"}

### PatientSafety
{safety_response or "[Not routed to safety]"}

## Bottom Line
{result.get('bottom_line', '')}

## Diagnosis
{result.get('diagnosis', '')}

## Risk Level
{result.get('risk_level', '')}

## Recommendation
{result.get('recommendation', '')}

## Medical View
{result.get('medical_view', '')}

## GDPR/HIPAA View
{result.get('gdpr_hipaa_view', '')}

## Country View
{result.get('country_view', '')}

## Implementation
{result.get('implementation', '')}

## Escalations
{result.get('escalations', '')}

## Veto Assessment
{result.get('veto', '')}

---
*Generated by CMedO Agent with sub-agent routing*
*Saved to vault: {vault_path}*
"""
        vault_path.write_text(frontmatter, encoding="utf-8")
        result["vault_path"] = str(vault_path)

    return result
