"""Main crew for AI Council with memory integration."""

import os
from crewai import Crew
from .agents import get_core_agents
from .tasks import (
    intelligence_task,
    devils_advocate_task,
    coach_task,
    synthesis_task
)
from .memory import get_memory_service


def run_council(topic: str, save_to_memory: bool = True) -> Crew:
    """Run a focused council session on the given topic.

    Args:
        topic: The business topic to evaluate
        save_to_memory: Whether to save results to memory service
    """
    # Check memory service availability
    memory = get_memory_service()
    memory_available = memory.health_check() if os.environ.get("DISABLE_MEMORY") != "true" else False

    # Get previous council context if available
    previous_councils = []
    if memory_available:
        try:
            previous_councils = memory.get_previous_councils(limit=3)
        except:
            pass

    # Build context string from previous councils
    context_note = ""
    if previous_councils:
        context_note = "\n\n## Previous Council Sessions (for continuity)\n"
        for council in previous_councils[:2]:
            context_note += f"- {council.get('metadata', {}).get('topic', council.get('content', '')[:100])}...\n"

    # Add context to topic
    enhanced_topic = topic + context_note

    # Create tasks
    intel_task = intelligence_task(enhanced_topic)
    da_task = devils_advocate_task(enhanced_topic, context=[intel_task])
    coach_t = coach_task(enhanced_topic, context=[intel_task, da_task])
    synthesis = synthesis_task(context=[intel_task, da_task, coach_t])

    crew = Crew(
        agents=get_core_agents(),
        tasks=[intel_task, da_task, coach_t, synthesis],
        verbose=True,
    )

    # Attach memory service to crew for post-execution saving
    crew.memory_service = memory if memory_available else None
    crew.topic = topic

    return crew


def execute_council_with_memory(topic: str) -> dict:
    """Execute council and save results to memory.

    Returns:
        dict with 'result', 'task_outputs', and 'memory_id' if saved
    """
    crew = run_council(topic, save_to_memory=True)

    print(f"🎯 Starting AI Council session on: {topic}")
    if crew.memory_service:
        print("📝 Memory service connected - results will be saved")
    print("=" * 60)

    result = crew.kickoff()

    # Extract outputs
    outputs = {}
    for task in crew.tasks:
        outputs[task.description.split('\n')[0][:80]] = task.output

    # Save to memory if available
    memory_id = None
    if crew.memory_service:
        try:
            # Generate recommendation from synthesis output
            recommendation = str(result)[:500] if result else ""
            memory_resp = crew.memory_service.save_council_result(
                topic=topic,
                result=str(result),
                agents=[a.role for a in crew.agents],
                recommendation=recommendation
            )
            memory_id = memory_resp.get("id")
            print(f"💾 Saved to memory: {memory_id}")
        except Exception as e:
            print(f"⚠️ Memory save failed: {e}")

    return {
        "result": result,
        "task_outputs": outputs,
        "memory_id": memory_id
    }


def run_full_board(topic: str, agents: list, tasks: list) -> Crew:
    """Run a full board meeting with custom agents and tasks."""
    crew = Crew(
        agents=agents,
        tasks=tasks,
        verbose=True,
        process="hierarchical"
    )
    crew.topic = topic
    return crew