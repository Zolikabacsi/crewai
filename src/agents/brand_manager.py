"""Brand Manager Operational Agent — run_brand_task entry point.

run_brand_task() is the daemon entry point. It classifies the incoming brand task,
loads the relevant HubSpot prompt from the library, applies brand-voice methodology,
generates the deliverable, checks for clinical claims (routes to CMedO if needed),
and saves to vault.

Vault: /home/zoltan/srv/vault/Second Brain/raw/Aestas_Brand/

HubSpot library: ~/srv/repos/AI/AI prompts/HubSpot prompt library/
Brand-voice skill: ~/srv/repos/everything-claude-code/.agents/skills/brand-voice/SKILL.md
"""

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────────
_CREWAI_ROOT = Path(__file__).parent.parent.parent
_SRC_DIR = _CREWAI_ROOT / "src"
_HUBSPOT_DIR = _CREWAI_ROOT / "repos" / "AI" / "AI prompts" / "HubSpot prompt library"
_BRANDVOICE_SKILL = (
    _CREWAI_ROOT / "repos" / "everything-claude-code" /
    ".agents" / "skills" / "brand-voice" / "SKILL.md"
)
sys.path.insert(0, str(_CREWAI_ROOT))
sys.path.insert(0, str(_SRC_DIR))

from src.config import Config
from src.tools.second_brain_tool import SecondBrainKnowledgeTool

VAULT_ROOT = Path("/home/zoltan/srv/vault/Second Brain/raw/Aestas_Brand")
CLAUDE_BIN = Path("/home/zoltan/.local/bin/claude")

# ── Vault context helper ──────────────────────────────────────────────────────
_vault_tool = SecondBrainKnowledgeTool()


def _get_vault_context(question: str, sections: list[str] | None = None) -> str:
    """Fetch relevant vault context before calling brand agent."""
    try:
        ctx = _vault_tool._run(query=question, sections=sections)
        if ctx and "not found" not in ctx.lower()[:100] and "No results" not in ctx:
            return f"\n\n## Relevant Context from Second Brain Vault\n{ctx}\n"
    except Exception:
        pass
    return ""

# ── Aestas Healthcare context (injected into all brand tasks) ─────────────────
AESTAS_CONTEXT = """You are producing a brand deliverable for Aestas Healthcare Ltd.

COMPANY: Aestas Healthcare Ltd (Cyprus HE391166)
FOUNDER: Dr. Zoltan Szepkuti, MD
SERVICE: Cross-border subscription telemedicine — GP care for expats across Cyprus, Sweden, Hungary
POSITIONING: Physician-founded, EU cross-border competence — not a tech platform with doctors
MARKETS: Cyprus (primary), Sweden (max 180 days/year), Hungary (ER + Medicover private)
ARCHETYPE: Caregiver + Sage (compassionate expertise, physician authority)
VOICE: Evidence-based, warm, professional, unhurried. Patient-first framing. No over-promise.

VOICE HARD BANNS (delete any of these from output):
- Fake curiosity hooks ("Did you know...")
- "not X, just Y"
- "no fluff" declarations
- Forced lowercase
- LinkedIn thought-leader cadence
- Bait questions
- "Excited to share"
- Generic founder-journey filler
- Corny parentheticals
- Medical overreach: guaranteed, cures, best doctor, revolutionary treatment

COMPLIANCE: Any claim that a specific treatment achieves a clinical outcome must be flagged.
General service descriptions and physician qualifications are safe without review.
"""

# ── Task type → HubSpot prompt file mapping ────────────────────────────────────
_TASK_PROMPT_MAP = {
    "brand_story": "Brand Story Architect.md",
    "archetype": "Brand Archetype Identifier.md",
    "differentiation": "Brand Differentiation Analyzer.md",
    "activation": "Brand Activation Planner.md",
    "voice": "Brand Personality Profiler.md",
    "evolution": "Brand Evolution Roadmap.md",
    "persona": "Buyer Persona Validator.md",
    "ideal_customer": "Ideal Customer Profiler.md",
    "value_prop": "Value Proposition Optimizer.md",
    "messaging": "Messaging Hierarchy Builder.md",
    "competitive": "Competitive Voice Analysis.md",
    "campaign": "Campaign Concept Generator.md",
    "content_strategy": "Content Audit & Strategy.md",
    "copy_review": None,  # special: brand-voice based
    "general": None,       # use task prompt
}

# ── Keyword classifier ────────────────────────────────────────────────────────
_TASK_KEYWORDS = {
    "brand_story": ["story", "narrative", "origin", "brand story", "our story", "founder story"],
    "archetype": ["archetype", "brand personality", "personality"],
    "differentiation": ["differentiat", "unique", "competitor", "positioning", "unique value"],
    "activation": ["launch", "activate", "brand launch", "refresh", "rebrand"],
    "voice": ["voice", "tone", "writing style", "language", "copy voice"],
    "evolution": ["evolution", "roadmap", "brand development"],
    "persona": ["persona", "buyer", "customer profile", "patient archetype"],
    "ideal_customer": ["ideal customer", "target customer", "icp"],
    "value_prop": ["value proposition", "value prop", "evp"],
    "messaging": ["messaging", "messaging hierarchy", "key message"],
    "competitive": ["competitive", "competitor", "market position"],
    "campaign": ["campaign", "marketing campaign", "channel"],
    "content_strategy": ["content strategy", "content audit", "content plan"],
    "copy_review": ["review copy", "audit copy", "copy audit", "check this", "review this"],
}

_VAULT_FOLDERS = {
    "brand_story": "brand_story",
    "archetype": "brand_story",
    "differentiation": "positioning",
    "activation": "campaigns",
    "voice": "voice",
    "evolution": "brand_story",
    "persona": "personas",
    "ideal_customer": "personas",
    "value_prop": "positioning",
    "messaging": "positioning",
    "competitive": "positioning",
    "campaign": "campaigns",
    "content_strategy": "campaigns",
    "copy_review": "voice",
    "general": "brand_story",
}


def _classify_question(question: str) -> str:
    q_lower = question.lower()
    scores = {}
    for domain, keywords in _TASK_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in q_lower)
        scores[domain] = score
    if max(scores.values()) > 0:
        return max(scores, key=scores.get)
    return "general"


def _load_hubspot_prompt(filename: str) -> str:
    """Load a HubSpot prompt file from the library."""
    path = _HUBSPOT_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"[HubSpot prompt '{filename}' not found at {path}]"


def _load_brandvoice_skill() -> str:
    """Load the brand-voice skill for source-derived voice extraction."""
    if _BRANDVOICE_SKILL.exists():
        return _BRANDVOICE_SKILL.read_text(encoding="utf-8")
    return "[brand-voice skill not found]"


def _extract_voice_from_content(content: str, source_name: str = "provided content") -> str:
    """Use brand-voice skill to extract voice profile from real Aestas copy."""
    skill = _load_brandvoice_skill()
    prompt = f"""{AESTAS_CONTEXT}

---

## TASK: Extract Voice Profile from Real Copy

{source_name}:

---
{content}
---

Using the brand-voice skill methodology:
1. Analyze the copy for: rhythm/sentence length, compression, capitalization, parenthetical use, question frequency, claim sharpness, what NEVER appears
2. Produce a VOICE PROFILE block

{service}

---
SERVICE ANALYSIS:
---
"""

    env = {
        "HOME": os.environ.get("HOME", "/home/zoltan"),
        "ANTHROPIC_API_KEY": Config.ANTHROPIC_AUTH_TOKEN or "",
        "ANTHROPIC_BASE_URL": Config.ANTHROPIC_BASE_URL or "https://chat.ultimateai.org",
    }

    try:
        result = subprocess.run(
            [str(CLAUDE_BIN), "-p",
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
            return parsed.get("result", parsed.get("content", ""))
        except json.JSONDecodeError:
            text = re.sub(r"^```json\s*", "", raw, flags=re.IGNORECASE)
            text = re.sub(r"^```\s*", "", text).strip().strip("`")
            try:
                inner = json.loads(text)
                return inner.get("result", inner.get("content", text))
            except json.JSONDecodeError:
                return text
    except Exception as e:
        return f"[VOICE EXTRACTION ERROR] {e}"


def _call_brand_agent(task_type: str, task: str, hubspot_prompt: str, voice_profile: str) -> str:
    """Call Claude Code with the HubSpot framework + voice profile + Aestas context."""
    # Pre-fetch relevant vault context for brand
    vault_ctx = _get_vault_context(task, sections=["Brand", "CMO"])

    prompt = f"""{AESTAS_CONTEXT}

---

## TASK TYPE: {task_type.upper()}

## USER REQUEST:
{task}

---

## VOICE PROFILE (from real Aestas copy):
{voice_profile}

---

## HUBSPOT FRAMEWORK:
{hubspot_prompt}
{vault_ctx}
---
## INSTRUCTION:
Apply the HubSpot framework above to the user request, using the Aestas Healthcare context and voice profile.
Produce a complete, actionable brand deliverable.
If clinical claims are present, flag them clearly at the end: ⚠️ CLINICAL CLAIMS REQUIRING CMEDO REVIEW
If no clinical claims, end with: ✅ NO CLINICAL CLAIMS — SAFE TO PUBLISH
"""
    env = {
        "HOME": os.environ.get("HOME", "/home/zoltan"),
        "ANTHROPIC_API_KEY": Config.ANTHROPIC_AUTH_TOKEN or "",
        "ANTHROPIC_BASE_URL": Config.ANTHROPIC_BASE_URL or "https://chat.ultimateai.org",
    }

    try:
        result = subprocess.run(
            [str(CLAUDE_BIN), "-p", 
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
            return parsed.get("result", parsed.get("content", ""))
        except json.JSONDecodeError:
            text = re.sub(r"^```json\s*", "", raw, flags=re.IGNORECASE)
            text = re.sub(r"^```\s*", "", text).strip().strip("`")
            try:
                inner = json.loads(text)
                return inner.get("result", inner.get("content", text))
            except json.JSONDecodeError:
                return text
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT] Claude Code timed out after 300s"
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}"


def _check_clinical_claims(text: str) -> bool:
    """Simple keyword check for potentially clinical claims."""
    clinical_keywords = [
        "treats", "cures", "heals", "prevents", "reduces risk",
        "proven to", "clinically proven", "medical guarantee",
        "best treatment", "most effective", "guaranteed outcome",
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in clinical_keywords)


def _save_to_vault(content: str, task: str, task_type: str) -> str:
    """Save brand deliverable to vault with YAML frontmatter."""
    safe_task = task[:50].replace("/", "-").replace(" ", "_").replace("'", "")
    filename = f"{date.today().isoformat()}_{safe_task}.md"
    folder = _VAULT_FOLDERS.get(task_type, "brand_story")
    save_path = VAULT_ROOT / folder / filename

    frontmatter = f"""---
title: "{task}"
type: {task_type}
created: {date.today().isoformat()}
tags: [brand, aestas]
---

"""
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(frontmatter + content)

    return str(save_path)


# ── Main entry point ───────────────────────────────────────────────────────────

def run_brand_task(task: str, task_type: str = None) -> dict:
    """Process a brand task: classify → HubSpot framework → voice → generate → save vault.

    Args:
        task: The brand task description
        task_type: Optional explicit type (brand_story, persona, differentiation, etc.)

    Returns:
        dict with keys: result (str), vault_path (str), task_type (str), clinical_flag (bool)
    """
    # 1. Classify if not specified
    if task_type is None:
        task_type = _classify_question(task)

    # 2. Load HubSpot prompt (or use generic if general)
    if task_type == "copy_review":
        hubspot_guidance = (
            "This is a COPY REVIEW task.\n"
            "Apply the brand-voice skill to audit the copy for:\n"
            "- Voice violations (LinkedIn cadence, fake hooks, overreach)\n"
            "- Medical claim overreach\n"
            "- Deviation from Aestas voice: evidence-based, warm, professional, unhurried\n"
        )
    elif task_type == "general":
        hubspot_guidance = (
            "This is a general brand advisory task.\n"
            "Provide a structured brand analysis and actionable recommendation.\n"
            "Apply Aestas context and voice principles throughout."
        )
    else:
        hubspot_guidance = _load_hubspot_prompt(_TASK_PROMPT_MAP.get(task_type, ""))

    # 3. Extract voice (use a minimal voice guide since we don't have real copy in daemon)
    # In production, the brand_manager should first fetch real copy from Drive
    voice_profile = """[Voice profile not yet derived from real Aestas copy. Apply the standard Aestas voice:
- Evidence-based, warm, professional, unhurried
- Patient-first framing
- No over-promise
- Specific claims over adjectives
- Plain language, no jargon
HARD BANNS: fake curiosity, "not X just Y", "no fluff", forced lowercase, LinkedIn cadence, medical overreach]
"""

    # 4. Generate deliverable
    result = _call_brand_agent(task_type, task, hubspot_guidance, voice_profile)

    # 5. Check for clinical claims
    clinical_flag = _check_clinical_claims(result)
    if clinical_flag:
        result += "\n\n⚠️ CLINICAL CLAIMS DETECTED — route to CMedO for sign-off before publishing"

    # 6. Save to vault
    vault_path = _save_to_vault(result, task, task_type)

    return {
        "result": result,
        "vault_path": vault_path,
        "task_type": task_type,
        "clinical_flag": clinical_flag,
        "question": task,
    }
