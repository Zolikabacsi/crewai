"""Task definitions for AI Council crew."""

from crewai import Task
from ..agents.agents import (
    CEOPartner, CFOPartner, CMOPartner, CTOPartner, COOPartner,
    CoFounderPartner, CoachPartner, IntelligencePartner,
    DevilsAdvocatePartner, AdvisorPartner, InvestorPartner, BoardMemberPartner
)


def create_board_meeting_task(topic: str) -> list[Task]:
    """Create a full board meeting task with all partners."""
    return [
        Task(
            description=f"Analyze this topic from a CEO perspective: {topic}",
            agent=CEOPartner(),
            expected_output="Strategic executive analysis with key decisions and recommendations"
        ),
        Task(
            description=f"Provide CFO perspective on: {topic}",
            agent=CFOPartner(),
            expected_output="Financial implications, resource requirements, and ROI analysis"
        ),
        Task(
            description=f"CMO view on: {topic}",
            agent=CMOPartner(),
            expected_output="Market positioning, customer impact, and growth strategy"
        ),
        Task(
            description=f"CTO assessment of: {topic}",
            agent=CTOPartner(),
            expected_output="Technical feasibility, risks, and technology strategy"
        ),
    ]


def create_quick_council_task(topic: str, context: list = None) -> Task:
    """Create a quick council task with core partners."""
    return Task(
        description=f"""Conduct a strategic council session on: {topic}

Bring together Co-Founder, Coach, Intelligence, and Devil's Advocate partners to provide integrated perspectives.

Each partner should contribute their view, then synthesize a consensus recommendation.
""",
        agent=CoFounderPartner(),
        expected_output="Integrated strategic recommendation from multiple partner perspectives",
        context=context
    )


def intelligence_task(topic: str, context: list = None) -> Task:
    return Task(
        description=f"Analyze market conditions and competitive landscape for: {topic}",
        agent=IntelligencePartner(),
        expected_output="Market intelligence brief with key insights and opportunities",
        context=context
    )


def devils_advocate_task(topic: str, context: list = None) -> Task:
    return Task(
        description=f"Stress test and identify weaknesses in: {topic}",
        agent=DevilsAdvocatePartner(),
        expected_output="Critical analysis of risks, flaws, and potential failure modes",
        context=context
    )


def coach_task(topic: str, context: list = None) -> Task:
    return Task(
        description=f"Provide founder guidance and performance perspective on: {topic}",
        agent=CoachPartner(),
        expected_output="Founder-focused advice on mindset, priorities, and execution",
        context=context
    )


def synthesis_task(context: list) -> Task:
    return Task(
        description="""Synthesize all partner perspectives into a final recommendation.

Review the inputs from all partners and create a structured consensus with:
- Key findings from each partner
- Areas of agreement and disagreement
- Final recommendation with rationale
- Suggested next steps
""",
        agent=AdvisorPartner(),
        expected_output="Comprehensive synthesis with final recommendation",
        context=context
    )