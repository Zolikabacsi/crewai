#!/usr/bin/env python3
"""Researcher Daemon — listens on AgentBus and provides market research.

Listens as 'Researcher', handles 'research_request' and 'ping' actions,
calls Claude Code with the research prompt, saves results to vault, and replies.

Vault path: /home/zoltan/srv/vault/Second Brain/raw/Aestas_Researcher/
"""

import json
import logging
import os
import re
import subprocess
import sys
import signal
from datetime import datetime
from pathlib import Path

# ── sys.path setup ──────────────────────────────────────────────────────────
# parent/parent of this script = ~/srv/crewai/scripts → ~/srv/crewai
_SCRIPT_DIR = Path(__file__).parent.resolve()
_CREWAI_ROOT = _SCRIPT_DIR.parent
_SRC_DIR = _CREWAI_ROOT / "src"
sys.path.insert(0, str(_CREWAI_ROOT))
sys.path.insert(0, str(_SRC_DIR))

# ── Imports ──────────────────────────────────────────────────────────────────
from src.agent_bus import AgentBus
from src.agents.researcher import run_researcher_task, RESEARCHER_PROMPT_PATH
from src.agent_logger import AgentLogger
from src.config import Config

# ── Paths ────────────────────────────────────────────────────────────────────
VAULT_ROOT = Path("/home/zoltan/srv/vault/Second Brain/raw/Aestas_Researcher")
LOG_PATH = Path("/home/zoltan/logs/researcher_daemon.log")

# ── Logging ───────────────────────────────────────────────────────────────────
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
logger = logging.getLogger("ResearcherDaemon")


# ── Research request handler ──────────────────────────────────────────────────

def _handle_research_request(question: str, bus: AgentBus = None) -> dict:
    """Process a research question, call run_researcher_task, return result dict."""
    logger.info("Processing research_request: %s", question[:100])

    # Signal task started so dashboard moves inbox → progress
    if bus:
        bus.broadcast(from_="Researcher", action="task.started", data={
            "agent": "Researcher", "question_preview": question[:100],
        })

    with AgentLogger(
        agent="researcher",
        task_name=question,
        vault_output_path=str(VAULT_ROOT),
    ) as run_log:
        try:
            result_data = run_researcher_task(question)
            run_log.finish(status="success", summary="Research task completed")
            log_path = str(run_log._log_file)
            return {**result_data, "log_path": log_path}
        except Exception as e:
            run_log.finish(status="failed", summary=f"{type(e).__name__}: {e}")
            logger.exception("run_researcher_task failed")
            return {"result": f"[ERROR] {type(e).__name__}: {e}", "vault_path": None, "log_path": str(run_log._log_file)}


# ── Main daemon loop ──────────────────────────────────────────────────────────

def main() -> None:
    """Start the Researcher daemon on AgentBus."""
    logger.info("Starting Researcher daemon")
    logger.info("VAULT_ROOT=%s", VAULT_ROOT)
    logger.info("RESEARCHER_PROMPT_PATH=%s", RESEARCHER_PROMPT_PATH)

    bus = AgentBus()
    agent_name = "Researcher"

    # Register with AgentBus before entering the receive loop
    bus.start_heartbeat(agent_name)
    bus.register(role=agent_name, metadata={"pid": os.getpid(), "type": "researcher"})
    logger.info("Registered as '%s' on AgentBus", agent_name)

    def shutdown(signum, frame) -> None:
        logger.info("Shutting down Researcher daemon on signal %d", signum)
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
            # Timeout — no message received within 300s, loop continues
            logger.debug("recv timeout (300s), continuing")
            continue

        # msg format: {"from": "...", "to": "...", "action": "...", "data": {...}}
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

        if action == "research_request":
            # data may be a dict with "question" key, or a raw string question
            if isinstance(data, dict):
                question = data.get("question", data.get("query", ""))
            else:
                question = str(data)

            if not question:
                logger.warning("research_request with empty question from %s", from_agent)
                bus.send(
                    to=from_agent,
                    from_=agent_name,
                    action="research_result",
                    data={"result": "[ERROR] Empty question received", "vault_path": None},
                )
                continue

            result_data = _handle_research_request(question, bus=bus)
            bus.send(
                to=from_agent,
                from_=agent_name,
                action="research_result",
                data=result_data,
            )
            continue

        # Unknown action
        logger.warning("Unknown action '%s' from %s, ignoring", action, from_agent)


if __name__ == "__main__":
    main()
