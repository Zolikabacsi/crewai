#!/usr/bin/env python3
"""RegulatoryAdvisor Daemon — listens on AgentBus and provides regulatory analysis.

Listens as 'RegulatoryAdvisor', handles 'regulatory_request' and 'ping' actions,
calls Claude Code with the regulatory prompt, saves results to vault, and replies.

Vault path: /home/zoltan/srv/vault/Second Brain/raw/Aestas_CMedO/regulations/
"""

import json
import logging
import os
import re
import subprocess
import sys
import uuid
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
from src.agents.regulatory_advisor import REGULATORY_PROMPT_PATH
from src.config import Config

# ── Paths ────────────────────────────────────────────────────────────────────
VAULT_ROOT = Path("/home/zoltan/srv/vault/Second Brain/raw/Aestas_CMedO")
VAULT_REGULATIONS = VAULT_ROOT / "regulations"
LOG_PATH = Path("/home/zoltan/logs/regulatory_advisor_daemon.log")

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
logger = logging.getLogger("RegulatoryAdvisorDaemon")


# ── Claude Code helper ────────────────────────────────────────────────────────

def _build_prompt(regulatory_prompt: str, question: str) -> str:
    """Build the full prompt sent to Claude Code."""
    return (
        "You are RegulatoryAdvisor for Aestas Healthcare.\n\n"
        f"{regulatory_prompt.strip()}\n\n"
        f"QUESTION: {question}\n\n"
        "Provide regulatory analysis for Hungary/EU."
    )


def _strip_markdown_fences(text: str) -> str:
    """Remove leading/closing markdown fences (```json / ```) from text."""
    text = text.strip()
    # Remove triple-backtick fences (with optional language tag)
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _call_claude_code(prompt: str, timeout: int = 180) -> str:
    """Call Claude Code as a subprocess and extract .result field from JSON."""
    env = {
        "ANTHROPIC_API_KEY": Config.ANTHROPIC_AUTH_TOKEN,
        "ANTHROPIC_BASE_URL": "https://chat.ultimateai.org",
    }

    cmd = [
        str(Path.home() / ".local" / "bin" / "claude"),
        "-p",
        "--model", "MiniMax-M2.7",
        "--output-format", "json",
    ]

    logger.info("Calling Claude Code with prompt length=%d", len(prompt))

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, **env},
        )
    except subprocess.TimeoutExpired:
        logger.error("Claude Code call timed out after %ds", timeout)
        raise RuntimeError(f"Claude Code call timed out after {timeout}s")

    if result.returncode != 0:
        logger.error("Claude Code stderr: %s", result.stderr)
        raise RuntimeError(f"Claude Code exited with code {result.returncode}: {result.stderr}")

    raw = result.stdout.strip()
    logger.debug("Claude Code raw response: %s", raw[:500])

    try:
        parsed = json.loads(raw)
        # Try .result field first (standard format)
        if isinstance(parsed, dict) and "result" in parsed:
            return parsed["result"]
        # Fallback: return the whole parsed object as string
        return json.dumps(parsed, ensure_ascii=False)
    except json.JSONDecodeError:
        # Not JSON — treat raw output as the result
        return _strip_markdown_fences(raw)


# ── Vault save ────────────────────────────────────────────────────────────────

def _save_to_vault(content: str, question: str) -> Path:
    """Save regulatory analysis to vault with YAML frontmatter."""
    VAULT_REGULATIONS.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    # Sanitise question into a short filename slug
    slug = re.sub(r"[^\w\s-]", "", question)[:60].replace(" ", "_").lower()
    filename = f"{date_str}_{slug}.md"
    vault_path = VAULT_REGULATIONS / filename

    # Build frontmatter
    frontmatter = {
        "date": now.isoformat(timespec="seconds"),
        "question": question,
        "model": "MiniMax-M2.7",
        "agent": "RegulatoryAdvisor",
    }

    md_content = "---\n"
    for key, val in frontmatter.items():
        md_content += f"{key}: {val}\n"
    md_content += "---\n\n"
    md_content += content

    vault_path.write_text(md_content, encoding="utf-8")
    logger.info("Saved regulatory analysis to %s", vault_path)
    return vault_path


# ── Regulatory request handler ───────────────────────────────────────────────

def _handle_regulatory_request(question: str) -> dict:
    """Process a regulatory question, call Claude Code, save to vault, return result dict."""
    logger.info("Processing regulatory_request: %s", question[:100])

    # 1. Load regulatory prompt
    if REGULATORY_PROMPT_PATH.exists():
        regulatory_prompt = REGULATORY_PROMPT_PATH.read_text(encoding="utf-8")
    else:
        logger.warning("REGULATORY_PROMPT_PATH not found: %s", REGULATORY_PROMPT_PATH)
        regulatory_prompt = ""

    # 2. Build prompt
    full_prompt = _build_prompt(regulatory_prompt, question)

    # 3. Call Claude Code
    try:
        result_text = _call_claude_code(full_prompt, timeout=180)
    except Exception as e:
        logger.exception("Claude Code call failed")
        return {"result": f"[ERROR] {type(e).__name__}: {e}", "vault_path": None}

    # 4. Strip markdown fences
    clean_result = _strip_markdown_fences(result_text)

    # 5. Save to vault
    try:
        vault_path = _save_to_vault(clean_result, question)
        vault_path_str = str(vault_path)
    except Exception as e:
        logger.exception("Failed to save to vault")
        vault_path_str = None

    return {"result": clean_result, "vault_path": vault_path_str}


# ── Main daemon loop ──────────────────────────────────────────────────────────

def main() -> None:
    """Start the RegulatoryAdvisor daemon on AgentBus."""
    logger.info("Starting RegulatoryAdvisor daemon")
    logger.info("VAULT_ROOT=%s", VAULT_ROOT)
    logger.info("VAULT_REGULATIONS=%s", VAULT_REGULATIONS)
    logger.info("REGULATORY_PROMPT_PATH=%s", REGULATORY_PROMPT_PATH)

    bus = AgentBus()
    agent_name = "RegulatoryAdvisor"

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
                action="regulatory_result",
                data={"result": "pong", "vault_path": None},
            )
            continue

        if action == "regulatory_request":
            # data may be a dict with "question" key, or a raw string question
            if isinstance(data, dict):
                question = data.get("question", data.get("query", ""))
            else:
                question = str(data)

            if not question:
                logger.warning("regulatory_request with empty question from %s", from_agent)
                bus.send(
                    to=from_agent,
                    from_=agent_name,
                    action="regulatory_result",
                    data={"result": "[ERROR] Empty question received", "vault_path": None},
                )
                continue

            result_data = _handle_regulatory_request(question)
            bus.send(
                to=from_agent,
                from_=agent_name,
                action="regulatory_result",
                data=result_data,
            )
            continue

        # Unknown action
        logger.warning("Unknown action '%s' from %s, ignoring", action, from_agent)


if __name__ == "__main__":
    main()
