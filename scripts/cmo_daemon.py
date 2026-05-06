#!/usr/bin/env python3
"""CMO Daemon — listens on AgentBus, delegates marketing work to sub-agents.

All task runs are logged to ~/srv/logs/cmo/runs/ with structured step/error tracking.
Generated artefacts are saved to the Second Brain vault as before.
"""
import os, sys, json, signal, datetime
from pathlib import Path

# PYTHONPATH for sibling packages
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.agent_bus import AgentBus
from src.marketing.crew import run_marketing_campaign
from src.agent_logger import AgentLogger

VAULT_ROOT = Path("/home/zoltan/srv/vault/Second Brain/raw/Aestas_CMO")
LOG_FILE   = Path("/home/zoltan/logs/cmo_daemon.log")

def log(msg: str):
    """Write to both stdout and log file."""
    print(msg)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.datetime.now().isoformat()} | {msg}\n")


def save_output_to_vault(result, output_type: str, task: str) -> tuple[str, str]:
    """Save CMO output to vault with YAML frontmatter.

    Returns:
        (save_path, slug) — absolute vault path and filename slug
    """
    # Serialize result to markdown
    if isinstance(result, dict):
        content = json.dumps(result, indent=2, ensure_ascii=False)
    else:
        content = str(result)

    # Build safe filename
    safe_task = task[:50].replace("/", "-").replace(" ", "_").replace("'", "")
    slug = f"{datetime.date.today().isoformat()}_{safe_task}"
    filename = f"{slug}.md"

    type_to_folder = {
        "seo": "seo_briefs",
        "social": "social_posts",
        "copy": "copy",
        "campaign": "campaigns",
        "brand_strategy": "brand",
        "content": "content",
    }
    folder = type_to_folder.get(output_type, "content")
    save_path = VAULT_ROOT / folder / filename

    # Build YAML frontmatter
    frontmatter = f"""---
title: "{task}"
type: {output_type}
created: {datetime.date.today().isoformat()}
tags: [cmo, aestas]
---

"""

    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(frontmatter + content)

    log(f"[CMO] Saved artefact to: {save_path}")
    return str(save_path), slug


def handle_request(msg: dict, bus: AgentBus) -> None:
    """Handle incoming marketing_request."""
    data = msg.get("data", {})
    task = data.get("task", "Write a LinkedIn post about Aestas Healthcare")
    output_type = data.get("type", "content")
    from_agent = msg.get("from", "unknown")

    log(f"[CMO] Received task from {from_agent}: {task[:80]}")

    # Signal task started so dashboard moves inbox → progress
    bus.broadcast(from_="CMO", action="task.started", data={
        "agent": "CMO", "question_preview": task[:100],
    })

    # Wrap entire task run in structured logging
    with AgentLogger(
        agent="cmo",
        task_name=task,
        retention_days=7,
    ) as run_log:
        run_log.step("task_received", {
            "from": from_agent,
            "output_type": output_type,
            "task_preview": task[:100],
        })

        try:
            # ── Run the marketing crew ──────────────────────────────────
            run_log.step("crew_start")
            result = run_marketing_campaign(task)
            run_log.step("crew_complete", {
                "result_type": type(result).__name__,
                "result_size_chars": len(str(result)),
            })

            # ── Save artefact to vault ─────────────────────────────────
            vault_path, slug = save_output_to_vault(result, output_type, task)
            run_log.capture_output(result, vault_path=vault_path)
            run_log.step("artefact_saved", {"vault_path": vault_path, "slug": slug})

            # ── Determine summary ───────────────────────────────────────
            if isinstance(result, dict):
                summary = f"CMO completed {output_type} task. "
                if output_type == "brand_strategy":
                    summary += "Brand strategy generated with positioning, pillars, content themes, bios, and 3 LinkedIn posts."
                else:
                    summary += f"Output keys: {list(result.keys())}."
            else:
                summary = f"CMO task completed. Result type: {type(result).__name__}, size: {len(str(result))} chars."

            # ── Respond via bus ─────────────────────────────────────────
            if isinstance(result, dict):
                output_text = str(result)[:2000]
            else:
                output_text = str(result)[:2000]

            bus.send(
                to=from_agent,
                from_="cmo",
                action="marketing_result",
                data={
                    "status": "complete",
                    "output": output_text,
                    "vault_path": vault_path,
                    "task": task,
                    "log_path": str(run_log._log_file),
                    "summary": summary,
                }
            )

            run_log.finish(status="success", summary=summary, vault_path=vault_path)
            log(f"[CMO] Run complete. Log: {run_log._log_file}")

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            run_log.error(e, traceback_str=tb)
            run_log.step("handle_exception", {"exception": str(e)})

            bus.send(
                to=from_agent,
                from_="cmo",
                action="marketing_result",
                data={"status": "error", "error": str(e), "task": task}
            )

            run_log.finish(status="failed", summary=f"CMO task failed: {e}")
            log(f"[CMO] Run failed: {e}")


def main():
    log("[CMO] Daemon starting, listening on agent.cmo...")
    bus = AgentBus()
    agent_name = "cmo"

    bus.start_heartbeat(agent_name)
    bus.register(role=agent_name, metadata={"pid": os.getpid(), "type": "cmo"})
    log(f"[CMO] Registered as '{agent_name}' on AgentBus")

    def shutdown(signum, frame):
        log("[CMO] Shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        try:
            msg = bus.recv(agent_name="cmo", timeout=60)
            if msg:
                action = msg.get("action", "")
                if action == "marketing_request":
                    handle_request(msg, bus)
                elif action == "ping":
                    bus.send(to=msg.get("from"), from_="cmo", action="pong", data={})
                else:
                    log(f"[CMO] Unknown action: {action}")
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"[CMO] Error in main loop: {e}")
            continue


if __name__ == "__main__":
    main()
