"""Task definitions for the business idea evaluator crew.

Each task is designed to guide its assigned agent through a specific
evaluation phase, with clear context, expected outputs, and dependencies.
"""

from crewai import Task
from ..agents import (
    MarketResearcher,
    FinancialAnalyst,
    RiskAssessor,
    BusinessWriter,
)


def market_research_task(business_idea: str, context: list = None) -> Task:
    """Create the market research task for the MarketResearcher agent.

    Args:
        business_idea: Description of the business idea to analyze
        context: Optional list of previous task outputs for context

    Returns:
        Configured Task instance
    """
    return Task(
        description=(
            f"Analyze the market landscape for the following business idea:\n\n"
            f"{business_idea}\n\n"
            "Your analysis should cover:\n"
            "1. Total Addressable Market (TAM), Serviceable Addressable Market (SAM), "
            "and Serviceable Obtainable Market (SOM)\n"
            "2. Market growth rate and projected trends (5-10 year horizon)\n"
            "3. Key market drivers and barriers\n"
            "4. Main competitors and their market share\n"
            "5. Target customer segments and personas\n"
            "6. Market trends and emerging opportunities\n\n"
            "Provide specific data points and cite sources where possible."
        ),
        agent=MarketResearcher(),
        expected_output=(
            "A comprehensive market analysis covering TAM/SAM/SOM, competitive landscape, "
            "target segments, and growth projections with supporting data."
        ),
        context=context,
    )


def financial_analysis_task(business_idea: str, context: list = None) -> Task:
    """Create the financial analysis task for the FinancialAnalyst agent.

    Args:
        business_idea: Description of the business idea to analyze
        context: Optional list of previous task outputs for context

    Returns:
        Configured Task instance
    """
    return Task(
        description=(
            f"Perform a thorough financial evaluation of this business idea:\n\n"
            f"{business_idea}\n\n"
            "Your analysis should include:\n"
            "1. Startup cost estimates and capital requirements\n"
            "2. Operating cost structure (fixed vs variable)\n"
            "3. Revenue model and pricing strategy\n"
            "4. Break-even analysis and timeline to profitability\n"
            "5. Funding requirements and runway\n"
            "6. Key financial metrics and KPIs\n"
            "7. Scenario analysis (conservative, moderate, optimistic)\n\n"
            "Provide specific numbers and assumptions where possible."
        ),
        agent=FinancialAnalyst(),
        expected_output=(
            "A detailed financial assessment including cost structure, revenue projections, "
            "break-even analysis, and funding requirements with clear assumptions."
        ),
        context=context,
    )


def risk_assessment_task(business_idea: str, context: list = None) -> Task:
    """Create the risk assessment task for the RiskAssessor agent.

    Args:
        business_idea: Description of the business idea to analyze
        context: Optional list of previous task outputs for context

    Returns:
        Configured Task instance
    """
    return Task(
        description=(
            f"Conduct a comprehensive risk assessment for this business idea:\n\n"
            f"{business_idea}\n\n"
            "Your analysis should identify and evaluate:\n"
            "1. Market risks (demand uncertainty, competition, regulatory changes)\n"
            "2. Operational risks (supply chain, technology, talent availability)\n"
            "3. Financial risks (cash flow, funding access, cost overruns)\n"
            "4. Legal/Regulatory risks (compliance, IP, contracts)\n"
            "5. External risks (economic conditions, geopolitical, natural disasters)\n\n"
            "For each risk, provide:\n"
            "- Probability (Low/Medium/High)\n"
            "- Impact (Low/Medium/High)\n"
            "- Mitigation strategies\n\n"
            "Provide an overall risk score and recommendations."
        ),
        agent=RiskAssessor(),
        expected_output=(
            "A structured risk assessment covering all risk categories with probability, "
            "impact ratings, and actionable mitigation strategies."
        ),
        context=context,
    )


def report_writing_task(context: list) -> Task:
    """Create the final report writing task for the BusinessWriter agent.

    This task depends on all previous analyses and synthesizes them into
    a comprehensive business evaluation report.

    Args:
        context: List of previous task outputs (market, financial, risk analyses)

    Returns:
        Configured Task instance
    """
    return Task(
        description=(
            "You are the final step in evaluating this business idea. Your colleagues "
            "have completed:\n"
            "1. Market Research Analysis\n"
            "2. Financial Analysis\n"
            "3. Risk Assessment\n\n"
            "Synthesize all of their findings into a comprehensive executive report that includes:\n\n"
            "1. Executive Summary (2-3 sentences on viability)\n"
            "2. Business Overview\n"
            "3. Market Opportunity Summary\n"
            "4. Financial Viability Summary\n"
            "5. Risk Profile Summary\n"
            "6. Recommendations (Go/No-Go with conditions)\n"
            "7. Next Steps\n\n"
            "The report should be professional, data-driven, and actionable. "
            "Format it clearly with headers and bullet points where appropriate."
        ),
        agent=BusinessWriter(),
        expected_output=(
            "A professional executive report synthesizing all analyses with clear "
            "recommendations and next steps for the business idea evaluation."
        ),
        context=context,
    )