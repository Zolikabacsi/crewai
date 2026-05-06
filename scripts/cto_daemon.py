#!/usr/bin/env python3
"""CTO Daemon — listens on AgentBus, handles technology evaluation, build vs. buy, and architecture review.

Listens as 'CTO', handles 'cto_request' and 'ping' actions,
calls run_cto_task() which routes to the right sub-agent (TechStackEvaluator/BuildVsBuyAgent/ArchitectureReviewAgent),
saves results to vault, and replies.

Vault path: /home/zoltan/srv/vault/Second Brain/raw/Aestas_CTO/
"""

import logging
import os
import re
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── sys/path setup ────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).parent.resolve()
_CREWAI_ROOT = _SCRIPT_DIR.parent
_SRC_DIR = _CREWAI_ROOT / "src"
sys.path.insert(0, str(_CREWAI_ROOT))
sys.path.insert(0, str(_SRC_DIR))

# ── Imports ───────────────────────────────────────────────────────────────────
from src.agent_bus import AgentBus
from src.agents.cto import run_cto_task
from src.agent_logger import AgentLogger

# ── Paths ─────────────────────────────────────────────────────────────────────
VAULT_ROOT = Path("/home/zoltan/srv/vault/Second Brain/raw/Aestas_CTO")
LOG_PATH = Path("/home/zoltan/logs/cto_daemon.log")

# ── Logging ──────────────────────────────────────────────────────────────────
_LOG_DIR = LOG_PATH.parent
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("CTODaemon")


def main() -> None:
    """Start the CTO daemon on AgentBus."""
    logger.info("Starting CTO daemon")
    logger.info("VAULT_ROOT=%s", VAULT_ROOT)

    bus = AgentBus()
    agent_name = "CTO"

    # Register with AgentBus before entering the receive loop
    bus.start_heartbeat(agent_name)
    bus.register(role=agent_name, metadata={"pid": os.getpid(), "type": "cto"})
    logger.info("Registered as '%s' on AgentBus", agent_name)

    def shutdown(signum, frame) -> None:
        logger.info("Shutting down CTO daemon on signal %d", signum)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("Listening on AgentBus as '%s' with timeout=300s", agent_name)

    while True:
        try:
            msg = bus.recv(agent_name=agent_name, timeout=300)
        except Exception as e:
            logger.exception("Error receiving message, retrying in 5s")
            import time; time.sleep(5)
            continue

        if msg is None:
            logger.debug("recv timeout (300s), continuing")
            continue

        from_agent = msg.get("from", "unknown")
        action = msg.get("action", "")
        data = msg.get("data", {})

        logger.info("Received from=%s action=%s", from_agent, action)

        if action == "ping":
            logger.debug("Responding pong to %s", from_agent)
            bus.send(
                to=from_agent,
                from_=agent_name,
                action="pong",
                data={"result": "pong", "vault_path": None},
            )
            continue

        if action == "cto_request":
            if isinstance(data, dict):
                question = data.get("question", data.get("query", ""))
            else:
                question = str(data)

            if not question:
                logger.warning("cto_request with empty question from %s", from_agent)
                bus.send(
                    to=from_agent,
                    from_=agent_name,
                    action="cto_result",
                    data={"result": "[ERROR] Empty question received", "vault_path": None, "domain": None},
                )
                continue

            logger.info("Processing cto_request: %s", question[:100])

            # Extract domain for logging before the wrapper
            domain = data.get("domain") if isinstance(data, dict) else None

            # Signal task started so dashboard moves inbox → progress
            bus.broadcast(from_=agent_name, action="task.started", data={
                "agent": agent_name, "question_preview": question[:100],
            })

            with AgentLogger(agent="cto", task_name=question, vault_output_path=VAULT_ROOT) as run_log:
                run_log.step("task_received", {"question_preview": question[:100], "domain": domain})
                try:
                    run_log.step("cto_task_start")
                    result = run_cto_task(question)
                    vault_path = result.get("vault_path") if isinstance(result, dict) else None
                    output_text = result.get("result", str(result))[:3000] if isinstance(result, dict) else str(result)[:3000]
                    summary = f"CTO completed task in {len(str(result))} chars."

                    run_log.capture_output(result, vault_path=vault_path)
                    run_log.finish(status="success", summary=summary, vault_path=vault_path)

                    bus.send(to=from_agent, from_=agent_name, action="cto_result", data={
                        "status": "complete", "result": output_text, "vault_path": vault_path,
                        "domain": domain, "question": question, "log_path": str(run_log._log_file),
                    })
                except Exception as e:
                    import traceback
                    run_log.error(e, traceback_str=traceback.format_exc())
                    run_log.finish(status="failed", summary=f"CTO task failed: {e}")
                    bus.send(to=from_agent, from_=agent_name, action="cto_result", data={
                        "status": "error", "error": str(e), "question": question,
                        "log_path": str(run_log._log_file),
                    })
            continue

        logger.warning("Unknown action '%s' from %s, ignoring", action, from_agent)


if __name__ == "__main__":
    main()
