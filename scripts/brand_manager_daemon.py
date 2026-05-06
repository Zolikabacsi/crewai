#!/usr/bin/env python3
"""Brand Manager Daemon — listens on AgentBus, handles brand tasks.

Listens as 'Brand', handles 'brand_request' and 'ping' actions,
calls run_brand_task() which loads HubSpot prompts + brand-voice methodology,
saves results to vault, and replies.

Vault path: /home/zoltan/srv/vault/Second Brain/raw/Aestas_Brand/
HubSpot library: ~/srv/repos/AI/AI prompts/HubSpot prompt library/
"""

import logging
import os
import re
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── sys/path setup ─────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).parent.resolve()
_CREWAI_ROOT = _SCRIPT_DIR.parent
_SRC_DIR = _CREWAI_ROOT / "src"
sys.path.insert(0, str(_CREWAI_ROOT))
sys.path.insert(0, str(_SRC_DIR))

# ── Imports ────────────────────────────────────────────────────────────────────
from src.agent_bus import AgentBus
from src.agent_logger import AgentLogger
from src.agents.brand_manager import run_brand_task

# ── Paths ─────────────────────────────────────────────────────────────────────
VAULT_ROOT = Path("/home/zoltan/srv/vault/Second Brain/raw/Aestas_Brand")
LOG_PATH = Path("/home/zoltan/logs/brand_manager_daemon.log")

# ── Logging ────────────────────────────────────────────────────────────────────
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
logger = logging.getLogger("BrandManagerDaemon")


def main() -> None:
    """Start the Brand Manager daemon on AgentBus."""
    logger.info("Starting Brand Manager daemon")
    logger.info("VAULT_ROOT=%s", VAULT_ROOT)

    bus = AgentBus()
    agent_name = "Brand"

    # Register with AgentBus before entering the receive loop
    bus.start_heartbeat(agent_name)
    bus.register(role=agent_name, metadata={"pid": os.getpid(), "type": "brand_manager"})
    logger.info("Registered as '%s' on AgentBus", agent_name)

    def shutdown(signum, frame) -> None:
        logger.info("Shutting down Brand Manager daemon on signal %d", signum)
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

        if action == "brand_request":
            if isinstance(data, dict):
                task = data.get("task", data.get("question", data.get("query", "")))
                task_type = data.get("type", None)  # optional explicit type
            else:
                task = str(data)
                task_type = None

            task_name = data.get("task", data.get("question", "brand_request")) if isinstance(data, dict) else "brand_request"

            if not task:
                logger.warning("brand_request with empty task from %s", from_agent)
                bus.send(
                    to=from_agent,
                    from_=agent_name,
                    action="brand_result",
                    data={"result": "[ERROR] Empty task received", "vault_path": None, "task_type": None, "clinical_flag": False},
                )
                continue

            logger.info("Processing brand_request: %s", task[:100])

            # Signal task started so dashboard moves inbox → progress
            bus.broadcast(from_=agent_name, action="task.started", data={
                "agent": agent_name, "question_preview": task[:100],
            })

            with AgentLogger(agent="brand", task_name=task_name) as run_log:
                try:
                    result_data = run_brand_task(task, task_type=task_type)
                    run_log.step("task_complete")
                    clinical_note = " ⚠️ CLINICAL CLAIMS — route to CMedO" if result_data.get("clinical_flag") else ""
                    logger.info(
                        "run_brand_task complete, type=%s, vault=%s, clinical=%s",
                        result_data.get("task_type"),
                        result_data.get("vault_path"),
                        result_data.get("clinical_flag"),
                    )

                    log_path = str(run_log.finish(status="success"))

                    bus.send(
                        to=from_agent,
                        from_=agent_name,
                        action="brand_result",
                        data={
                            "status": "complete",
                            "result": result_data.get("result", "")[:3000],
                            "vault_path": result_data.get("vault_path"),
                            "log_path": log_path,
                            "task_type": result_data.get("task_type"),
                            "clinical_flag": result_data.get("clinical_flag"),
                            "question": task,
                        },
                    )
                except Exception as e:
                    run_log.error(str(e))
                    logger.exception("run_brand_task failed")
                    log_path = str(run_log.finish(status="failed"))
                    bus.send(
                        to=from_agent,
                        from_=agent_name,
                        action="brand_result",
                        data={"status": "error", "error": str(e), "log_path": log_path, "question": task},
                    )
            continue

        # Unknown action
        logger.warning("Unknown action '%s' from %s, ignoring", action, from_agent)


if __name__ == "__main__":
    main()
