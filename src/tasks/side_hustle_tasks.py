"""Side hustle task definitions."""

from crewai import Task
from ..agents.side_hustle_scout import SideHustleScout


def side_hustle_scout_task(context: list = None) -> Task:
    """Run a side hustle scan — scrape web, consult council, route to Slack.

    Args:
        context: Optional list of previous task outputs.

    Returns:
        Configured Task instance.
    """
    return Task(
        description=(
            "Run a full side hustle opportunity scan:\n\n"
            "1. Use WebScraperTool to scrape reddit (r/startups, r/sidehustle), "
            "IndieHackers, Product Hunt, and Upwork for trending opportunities.\n"
            "2. Use IndustryReportTool to cross-reference vault documents for "
            "growing market segments and emerging needs.\n"
            "3. Evaluate each opportunity: income potential (€/month), time required "
            "(hrs/week), startup cost (€), skill match, market timing.\n"
            "4. MANDATORY: Consult CoachPartner and DevilsAdvocatePartner for EVERY opportunity.\n"
            "5. Selective: consult CFOPartner for financial validation, "
            "IntelligencePartner for market size.\n"
            "6. Classify as 'extraordinary' (immediate Slack alert) or 'regular' (daily report).\n"
            "7. Store all opportunities via OpportunityStorageTool (action='save').\n"
            "8. Send Slack notification via SlackClient (immediate for extraordinary, "
            "daily report for regular).\n\n"
            "Use the SlackClient from slack.slack_client to build and send messages. "
            "Set SLACK_WEBHOOK_URL env var to enable Slack sending."
        ),
        agent=SideHustleScout(),
        expected_output=(
            "A list of discovered opportunities with scores and council feedback, "
            "stored in the opportunity store, and Slack notifications sent."
        ),
        context=context,
    )