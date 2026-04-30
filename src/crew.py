"""The main Crew orchestrator that coordinates agents and tasks."""

from crewai import Crew
from .agents import get_all_agents
from .tasks import (
    market_research_task,
    financial_analysis_task,
    risk_assessment_task,
    report_writing_task,
)
from .config import Config


def evaluate_business_idea(business_idea: str, verbose: bool = None) -> Crew:
    """Create and configure the business evaluation crew.

    Args:
        business_idea: The business idea description to evaluate
        verbose: Override for verbose mode (defaults to Config.VERBOSE)

    Returns:
        Configured Crew instance ready to kickoff()
    """
    # Create tasks - later tasks depend on earlier ones for context
    market_task = market_research_task(business_idea)
    financial_task = financial_analysis_task(
        business_idea, context=[market_task]
    )
    risk_task = risk_assessment_task(
        business_idea, context=[market_task, financial_task]
    )
    report_task = report_writing_task(
        context=[market_task, financial_task, risk_task]
    )

    # Create the crew with agents and tasks
    crew = Crew(
        agents=get_all_agents(),
        tasks=[
            market_task,
            financial_task,
            risk_task,
            report_task,
        ],
        verbose=verbose if verbose is not None else Config.VERBOSE,
        max_iterations=Config.MAX_ITERATIONS,
        # Process workflow: sequential by default (tasks run in order)
        # Use process=Process.hierarchical for manager-based delegation
    )

    return crew


def run_evaluation(business_idea: str, output_file: str = None) -> dict:
    """Run the full business evaluation and optionally save the report.

    Args:
        business_idea: The business idea to evaluate
        output_file: Optional path to save the final report

    Returns:
        Dictionary with task outputs and the final report
    """
    crew = evaluate_business_idea(business_idea)

    print("🚀 Starting business evaluation crew...")
    print(f"📋 Business idea: {business_idea[:100]}...")

    # Kickoff starts the crew workflow
    result = crew.kickoff()

    # Extract outputs from each task
    outputs = {}
    for task in crew.tasks:
        outputs[task.description.split('\n')[0][:80]] = task.output

    if output_file:
        # Save the final report to file
        import json
        from pathlib import Path

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump({
                'business_idea': business_idea,
                'task_outputs': outputs,
                'final_report': str(result),
            }, f, indent=2)

        print(f"💾 Report saved to: {output_file}")

    return {
        'result': result,
        'task_outputs': outputs,
    }