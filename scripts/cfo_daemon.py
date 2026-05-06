#!/usr/bin/env python3
"""CFO Daemon — listens on AgentBus, handles financial analysis, pricing, and ROI tasks.

Listens as 'CFO', handles 'cfo_request' and 'ping' actions,
calls run_cfo_task() which routes to the right sub-agent (FinancialAnalysis/PricingStrategy/ROI),
saves results to vault, and replies.

Vault path: /home/zoltan/srv/vault/Second Brain/raw/Aestas_CFO/
"""

import logging
import os
import re
import signal
import subprocess
import sys
import json
from datetime import datetime
from pathlib import Path

# ── sys.path setup ────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).parent.resolve()
_CREWAI_ROOT = _SCRIPT_DIR.parent
_SRC_DIR = _CREWAI_ROOT / "src"
sys.path.insert(0, str(_CREWAI_ROOT))
sys.path.insert(0, str(_SRC_DIR))

# ── Imports ───────────────────────────────────────────────────────────────────
from src.agent_bus import AgentBus
from src.agents.cfo import run_cfo_task
from src.agent_logger import AgentLogger

# ── Paths ─────────────────────────────────────────────────────────────────────
VAULT_ROOT = Path("/home/zoltan/srv/vault/Second Brain/raw/Aestas_CFO")
LOG_PATH = Path("/home/zoltan/logs/cfo_daemon.log")

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
logger = logging.getLogger("CFODaemon")


# ── Main daemon loop ──────────────────────────────────────────────────────────

def main() -> None:
    """Start the CFO daemon on AgentBus."""
    logger.info("Starting CFO daemon")
    logger.info("VAULT_ROOT=%s", VAULT_ROOT)

    bus = AgentBus()
    agent_name = "CFO"

    # Register with AgentBus before entering the receive loop
    bus.start_heartbeat(agent_name)
    bus.register(role=agent_name, metadata={"pid": os.getpid(), "type": "cfo"})
    logger.info("Registered as '%s' on AgentBus", agent_name)

    def shutdown(signum, frame) -> None:
        logger.info("Shutting down CFO daemon on signal %d", signum)
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

        if action == "cfo_request":
            # data may be a dict with "question"/"query" key, or a raw string
            if isinstance(data, dict):
                question = data.get("question", data.get("query", ""))
            else:
                question = str(data)

            if not question:
                logger.warning("cfo_request with empty question from %s", from_agent)
                bus.send(
                    to=from_agent,
                    from_=agent_name,
                    action="cfo_result",
                    data={"result": "[ERROR] Empty question received", "vault_path": None, "domain": None},
                )
                continue

            logger.info("Processing cfo_request: %s", question[:100])

            domain = data.get("domain") if isinstance(data, dict) else None

            # Signal task started so dashboard moves inbox → progress
            bus.broadcast(from_=agent_name, action="task.started", data={
                "agent": agent_name, "question_preview": question[:100],
            })

            with AgentLogger(agent="cfo", task_name=question, vault_output_path=VAULT_ROOT) as run_log:
                run_log.step("task_received", {"question_preview": question[:100], "domain": domain})
                try:
                    run_log.step("cfo_task_start")
                    result = run_cfo_task(question)
                    run_log.step("cfo_task_complete", {"result_keys": list(result.keys()) if isinstance(result, dict) else None})

                    # Build response data
                    if isinstance(result, dict):
                        output_text = result.get("result", str(result))[:3000]
                        vault_path = result.get("vault_path")
                        summary = f"CFO completed {domain or 'financial'} analysis task in {len(str(result))} chars."
                    else:
                        output_text = str(result)[:3000]
                        vault_path = None
                        summary = f"CFO task completed, result type: {type(result).__name__}"

                    run_log.capture_output(result, vault_path=vault_path)
                    run_log.finish(status="success", summary=summary, vault_path=vault_path)

                    bus.send(to=from_agent, from_=agent_name, action="cfo_result", data={
                        "status": "complete",
                        "result": output_text,
                        "vault_path": vault_path,
                        "domain": domain,
                        "question": question,
                        "log_path": str(run_log._log_file),
                    })
                except Exception as e:
                    import traceback
                    run_log.error(e, traceback_str=traceback.format_exc())
                    run_log.finish(status="failed", summary=f"CFO task failed: {e}")
                    bus.send(to=from_agent, from_=agent_name, action="cfo_result", data={
                        "status": "error",
                        "error": str(e),
                        "question": question,
                        "log_path": str(run_log._log_file),
                    })
            continue

        # Unknown action
        logger.warning("Unknown action '%s' from %s, ignoring", action, from_agent)


if __name__ == "__main__":
    main()
