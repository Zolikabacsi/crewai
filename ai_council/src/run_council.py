"""Council runner — consults the AI board partners on a given topic."""

import sys
import os
from pathlib import Path
from typing import Optional

# ai_council/src/run_council.py → 3 levels up = project root ~/srv/crewai/
_CREWAI_ROOT = str(Path(__file__).parent.parent.parent)
if _CREWAI_ROOT not in sys.path:
    sys.path.insert(0, _CREWAI_ROOT)

os.environ.setdefault("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_AUTH_TOKEN", ""))
os.environ.setdefault("ANTHROPIC_BASE_URL", os.environ.get("ANTHROPIC_BASE_URL", ""))

from crewai import Crew, Task
from crewai.process import Process

from .agents.agents import (
    CMOPartner,
    CFOPartner,
    CoachPartner,
    DevilsAdvocatePartner,
)
from .config import Config


# ─── helpers ────────────────────────────────────────────────────────────────

def _setup_llm_env():
    if Config.ANTHROPIC_AUTH_TOKEN:
        os.environ["ANTHROPIC_API_KEY"] = Config.ANTHROPIC_AUTH_TOKEN
    if Config.ANTHROPIC_BASE_URL:
        os.environ["ANTHROPIC_BASE_URL"] = Config.ANTHROPIC_BASE_URL.rstrip("/v1") + "/v1"


def _build_task(agent, topic: str, question: str) -> Task:
    return Task(
        description=(
            f"TOPIC: {topic}\n\n"
            f"YOUR QUESTION: {question}\n\n"
            "Give a focused, specific answer drawing on your board-role expertise. "
            "Be direct — no preamble, no summary headers. Output a single cohesive paragraph "
            "(2–4 sentences) with your assessment or recommendation."
        ),
        agent=agent,
        expected_output="Single paragraph with the partner's assessment.",
    )


# ─── main entry point ───────────────────────────────────────────────────────

def run_council(
    topic: str,
    partners: Optional[list[str]] = None,
) -> str:
    """
    Consult board partners on ``topic`` and return their opinions as a
    structured string.

    Args:
        topic: Description of the opportunity / question to put to the board.
        partners: List of partner class names to consult. Defaults to the
                  standard side-hustle quartet (CMO, CFO, Coach, Devil's Advocate).

    Returns:
        A string summarising each partner's view, prefixed with their role.
    """
    _setup_llm_env()

    if partners is None:
        partners = ["CMOPartner", "CFOPartner", "CoachPartner", "DevilsAdvocatePartner"]

    # Instantiate requested partners
    partner_map = {
        "CMOPartner":           CMOPartner,
        "CFOPartner":           CFOPartner,
        "CoachPartner":         CoachPartner,
        "DevilsAdvocatePartner": DevilsAdvocatePartner,
    }

    agents = []
    tasks  = []

    question_per_partner = {
        "CMOPartner": "As the CMO, assess the market viability, audience fit, "
                       "and marketing strategy for this opportunity. "
                       "Is there a clear GTM path? What channels look promising?",
        "CFOPartner": "As the CFO, evaluate the financial viability. "
                       "What are the startup costs, income potential, and unit economics? "
                       "Is this worth the time investment vs. other opportunities?",
        "CoachPartner": "As the Coach, evaluate founder fit. "
                         "Does this align with the founder's skills and lifestyle? "
                         "What mindset or execution risks do you see?",
        "DevilsAdvocatePartner": "As the Devil's Advocate, stress-test this opportunity. "
                                  "What could go wrong? What are the biggest risks, "
                                  "red flags, or failure modes? Be brutally honest.",
    }

    for name in partners:
        cls = partner_map.get(name)
        if cls is None:
            continue          # skip unknown partners silently
        agent = cls()
        agents.append(agent)
        q = question_per_partner.get(name, "What is your assessment of this opportunity?")
        tasks.append(_build_task(agent, topic, q))

    if not agents:
        return "[no valid partners selected]"

    # Sequential — each partner gives their opinion in turn (board meeting style)
    crew = Crew(
        agents=agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=Config.VERBOSE,
    )

    result = crew.kickoff()

    # Build structured response
    lines = ["🏛 *AI Board Partners — Assessment*\n"]
    for i, name in enumerate(partners):
        if name in partner_map:
            role = name.replace("Partner", "").replace("DevilsAdvocate", "Devil's Advocate")
            lines.append(f"*{role}:*\n{result.tasks_output[i].raw if hasattr(result.tasks_output[i], 'raw') else str(result.tasks_output[i])}\n")

    return "\n".join(lines)
