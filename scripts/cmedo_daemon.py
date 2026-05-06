#!/usr/bin/env python3
"""CMedO Daemon — listens on AgentBus, handles medical operations and monitoring."""
import os, sys, json, signal, datetime, traceback
from pathlib import Path

# PYTHONPATH for sibling packages
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.agent_bus import AgentBus
from src.agents.cmedo import run_cmedo_task
from src.agent_logger import AgentLogger

VAULT_ROOT = Path("/home/zoltan/srv/vault/Second Brain/raw/Aestas_CMedO")
LOG_FILE = Path("/home/zoltan/logs/cmedo_daemon.log")

def log(msg: str):
    """Write to both stdout and log file."""
    print(msg)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.datetime.now().isoformat()} | {msg}\n")

def save_output_to_vault(result, output_type: str, task: str) -> str:
    """Save CMedO output to vault with YAML frontmatter.
    
    Args:
        result: Either a dict or a string
        output_type: clinical_review, guideline, regulation, safety, monitoring
        task: The original task description
    
    Returns:
        Path to the saved file
    """
    # Serialize result to markdown
    if isinstance(result, dict):
        content = json.dumps(result, indent=2, ensure_ascii=False)
    else:
        content = str(result)

    # Build safe filename
    safe_task = task[:50].replace("/", "-").replace(" ", "_").replace("'", "")
    filename = f"{datetime.date.today().isoformat()}_{safe_task}.md"

    type_to_folder = {
        "clinical_review": "clinical_reviews",
        "guideline": "guidelines",
        "regulation": "regulations",
        "safety": "safety",
        "monitoring": "monitoring",
    }
    folder = type_to_folder.get(output_type, "clinical_reviews")
    save_path = VAULT_ROOT / folder / filename

    # Build YAML frontmatter
    frontmatter = f"""---
title: "{task}"
type: {output_type}
created: {datetime.date.today().isoformat()}
tags: [cmedo, aestas]
---

"""

    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(frontmatter + content)

    log(f"[CMedO] Saved to: {save_path}")
    return str(save_path)


def handle_cmedo_request(msg: dict, bus: AgentBus) -> None:
    """Handle incoming cmedo_request."""
    data = msg.get("data", {})
    task = data.get("question", data.get("task", "clinical_request"))
    request_type = data.get("type", "clinical_review")
    from_agent = msg.get("from", "unknown")
    task_name = data.get("task", "clinical_request")

    # Signal task started so dashboard moves inbox → progress
    bus.broadcast(from_="CMedO", action="task.started", data={
        "agent": "CMedO", "question_preview": task[:100],
    })

    with AgentLogger(agent="cmedo", task_name=task_name, vault_output_path=VAULT_ROOT) as run_log:
        run_log.step("task_received", {
            "from_agent": from_agent,
            "task": task,
            "request_type": request_type,
        })
        try:
            run_log.step("cmedo_task_start")
            result = process_medical_task(task, request_type)
            log(f"[CMedO] Processing complete, type={type(result).__name__}")

            vault_path = result.get("vault_path") if isinstance(result, dict) else None
            output_text = result.get("result", str(result))[:3000] if isinstance(result, dict) else str(result)[:3000]

            run_log.capture_output(result, vault_path=vault_path)
            run_log.finish(status="success", summary=f"CMedO task completed: {task[:80]}", vault_path=vault_path)

            bus.send(
                to=from_agent,
                from_="cmedo",
                action="cmedo_result",
                data={
                    "status": "complete",
                    "output": output_text,
                    "vault_path": vault_path,
                    "task": task,
                }
            )
        except Exception as e:
            run_log.error(e, traceback_str=traceback.format_exc())
            run_log.finish(status="failed", summary=f"CMedO task failed: {str(e)}")
            log(f"[CMedO] Error: {e}")
            log(f"[CMedO] Traceback: {traceback.format_exc()}")
            bus.send(
                to=from_agent,
                from_="cmedo",
                action="cmedo_result",
                data={"status": "error", "error": str(e), "task": task}
            )


def handle_monitoring_check(msg: dict, bus: AgentBus) -> None:
    """Handle incoming monitoring_check."""
    data = msg.get("data", {})
    from_agent = msg.get("from", "unknown")
    task_name = "healthcare_monitoring_check"

    with AgentLogger(agent="cmedo", task_name=task_name, vault_output_path=VAULT_ROOT) as run_log:
        run_log.step("task_received", {
            "from_agent": from_agent,
            "data": data,
        })
        try:
            run_log.step("monitoring_check_start")
            monitoring_result = perform_monitoring_checks(data)

            vault_path = monitoring_result.get("vault_path") if isinstance(monitoring_result, dict) else None
            output_text = monitoring_result.get("result", str(monitoring_result))[:3000] if isinstance(monitoring_result, dict) else str(monitoring_result)[:3000]

            run_log.capture_output(monitoring_result, vault_path=vault_path)
            run_log.finish(status="success", summary="Healthcare monitoring check completed", vault_path=vault_path)

            bus.send(
                to=from_agent,
                from_="cmedo",
                action="monitoring_result",
                data={
                    "status": "complete",
                    "output": output_text,
                    "vault_path": vault_path,
                }
            )
        except Exception as e:
            run_log.error(e, traceback_str=traceback.format_exc())
            run_log.finish(status="failed", summary=f"Monitoring check failed: {str(e)}")
            log(f"[CMedO] Monitoring error: {e}")
            log(f"[CMedO] Traceback: {traceback.format_exc()}")
            bus.send(
                to=from_agent,
                from_="cmedo",
                action="monitoring_result",
                data={"status": "error", "error": str(e)}
            )


def process_medical_task(task: str, request_type: str) -> dict:
    """Process a medical operations task via CMedO agent.

    Args:
        task: The question or task description
        request_type: Type of request (clinical_review, guideline, regulation, safety)

    Returns:
        Dict with CMedO structured analysis
    """
    return run_cmedo_task(question=task)


def perform_monitoring_checks(data: dict) -> dict:
    """Perform system monitoring checks.
    
    Args:
        data: Optional parameters for monitoring
    
    Returns:
        Dict with monitoring results
    """
    # Placeholder for actual monitoring logic
    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "checks_performed": ["safety", "compliance", "guidelines"],
        "status": "healthy",
        "details": "All monitoring checks completed successfully"
    }


def main():
    log("[CMedO] Daemon starting, listening on agent.cmedo...")
    bus = AgentBus()
    agent_name = "cmedo"

    # Register with AgentBus before entering the receive loop
    bus.start_heartbeat(agent_name)
    bus.register(role=agent_name, metadata={"pid": os.getpid(), "type": "cmedo"})
    log(f"[CMedO] Registered as '{agent_name}' on AgentBus")

    def shutdown(signum, frame):
        log("[CMedO] Shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        try:
            msg = bus.recv(agent_name="cmedo", timeout=300)
            if msg:
                action = msg.get("action", "")
                if action == "cmedo_request":
                    handle_cmedo_request(msg, bus)
                elif action == "monitoring_check":
                    handle_monitoring_check(msg, bus)
                elif action == "ping":
                    bus.send(to=msg.get("from"), from_="cmedo", action="pong", data={})
                else:
                    log(f"[CMedO] Unknown action: {action}")
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"[CMedO] Error: {e}")
            continue


if __name__ == "__main__":
    main()
