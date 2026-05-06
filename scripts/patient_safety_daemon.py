#!/usr/bin/env python3
"""PatientSafety Daemon — listens on AgentBus, handles patient safety questions.

Listens as 'PatientSafety' on the Redis AgentBus. For each safety_request:
1. Loads SAFETY_PROMPT.md content
2. Builds prompt with patient safety framework + question
3. Calls Claude Code (MiniMax-M2.7) with --output-format json
4. Extracts .result field, strips markdown fences
5. Saves to vault with YAML frontmatter (VAULT_ROOT/safety/YYYYMMDD_task.md)
6. Sends result back via bus.send(to=from_agent, action='safety_result', ...)
"""

import os
import sys
import json
import signal
import datetime
import subprocess
import re
from pathlib import Path

# ── sys.path setup ──────────────────────────────────────────────────────────────
# parent/parent of this file = ~/srv/crewai; add src/ for local package imports
_SCRIPT_DIR = Path(__file__).parent.resolve()          # .../crewai/scripts
_CREWAI_ROOT = _SCRIPT_DIR.parent                        # .../crewai
_SRC_DIR = _CREWAI_ROOT / "src"                          # .../crewai/src
sys.path.insert(0, str(_CREWAI_ROOT))
sys.path.insert(0, str(_SRC_DIR))

# ── Imports ───────────────────────────────────────────────────────────────────
from src.agent_bus import AgentBus
from src.config import Config

# ── Constants ──────────────────────────────────────────────────────────────────
VAULT_ROOT = Path("/home/zoltan/srv/vault/Second Brain/raw/Aestas_CMedO")
SAFETY_PROMPT_PATH = Path("/home/zoltan/srv/crewai/ai_council/src/prompts/SAFETY_PROMPT.md")
LOG_FILE = Path("/home/zoltan/logs/patient_safety_daemon.log")
CLAUDE_BIN = Path.home() / ".local" / "bin" / "claude"

# ── Logging ───────────────────────────────────────────────────────────────────
def _ensure_log_dir():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

def log(msg: str):
    """Write to both stdout and log file."""
    _ensure_log_dir()
    timestamp = datetime.datetime.now().isoformat()
    line = f"{timestamp} | {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ── Environment setup for Claude Code ─────────────────────────────────────────
def _setup_env():
    """Set env vars required by Claude Code subprocess."""
    os.environ["ANTHROPIC_API_KEY"] = Config.ANTHROPIC_AUTH_TOKEN or ""
    os.environ["ANTHROPIC_BASE_URL"] = "https://chat.ultimateai.org"

# ── Safety Prompt loading ─────────────────────────────────────────────────────
def _load_safety_prompt() -> str:
    """Load the SAFETY_PROMPT.md content for framework context."""
    if SAFETY_PROMPT_PATH.exists():
        return SAFETY_PROMPT_PATH.read_text(encoding="utf-8")
    log(f"[WARN] SAFETY_PROMPT not found at {SAFETY_PROMPT_PATH}, using empty prompt")
    return ""

# ── Claude Code invocation ─────────────────────────────────────────────────────
def _call_claude_code(prompt: str, timeout: int = 180) -> str:
    """Call Claude Code subprocess and return JSON-decoded .result field.

    Args:
        prompt: Full prompt string to send to Claude Code
        timeout: Seconds before killing the subprocess (default 180)

    Returns:
        The .result field from Claude Code JSON output (stripped of markdown fences)

    Raises:
        RuntimeError: If Claude Code fails or returns non-zero exit
        ValueError: If JSON output cannot be parsed or .result is missing
    """
    cmd = [
        str(CLAUDE_BIN),
        "-p",
        "--model", "MiniMax-M2.7",
        "--output-format", "json",
    ]

    _setup_env()

    log(f"[Claude] Invoking Claude Code (timeout={timeout}s)...")
    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={
                "ANTHROPIC_API_KEY": Config.ANTHROPIC_AUTH_TOKEN or "",
                "ANTHROPIC_BASE_URL": "https://chat.ultimateai.org",
            },
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Claude Code timed out after {timeout}s") from e
    except FileNotFoundError:
        raise RuntimeError(f"Claude Code binary not found at {CLAUDE_BIN}")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        log(f"[Claude] stderr: {stderr}")
        raise RuntimeError(f"Claude Code exited with code {result.returncode}: {stderr}")

    raw_output = result.stdout.strip()
    log(f"[Claude] Raw output length: {len(raw_output)} chars")

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    cleaned = re.sub(r"^```json\s*", "", raw_output, flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude Code output is not valid JSON: {e}\nOutput was: {raw_output[:500]}") from e

    if "result" not in parsed:
        raise ValueError(f"Claude Code JSON output missing '.result' field. Keys: {list(parsed.keys())}")

    return parsed["result"]

# ── Vault saving ───────────────────────────────────────────────────────────────
def _strip_markdown_fences(text: str) -> str:
    """Remove leading/trailing markdown fences from text."""
    lines = text.splitlines()
    # Remove ```json or ``` prefix
    if lines and re.match(r"^```(json)?\s*$", lines[0], re.IGNORECASE):
        lines = lines[1:]
    if lines and re.match(r"^```\s*$", lines[-1], re.IGNORECASE):
        lines = lines[:-1]
    return "\n".join(lines).strip()

def _save_to_vault(content: str, task: str) -> str:
    """Save patient safety analysis result to vault with YAML frontmatter.

    File path: VAULT_ROOT/safety/YYYYMMDD_task.md

    Args:
        content: The analysis text to save
        task: The original question/task (used in frontmatter + filename)

    Returns:
        Absolute path to the saved file
    """
    safety_dir = VAULT_ROOT / "safety"
    safety_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.date.today()
    date_str = today.isoformat()  # YYYY-MM-DD

    # Build a safe filename slug
    safe_task = re.sub(r"[^a-zA-Z0-9_\-]+", "_", task)[:60].strip("_")
    filename = f"{date_str}_{safe_task}.md"
    filepath = safety_dir / filename

    # Build YAML frontmatter
    frontmatter = f"""---
title: "{task}"
agent: PatientSafety
date: {date_str}
type: patient_safety_analysis
tags: [patient_safety, aestas, cmedo]
vault_root: {str(VAULT_ROOT)}
---

"""

    filepath.write_text(frontmatter + content, encoding="utf-8")
    log(f"[Vault] Saved to: {filepath}")
    return str(filepath)

# ── Message handlers ───────────────────────────────────────────────────────────
def handle_safety_request(msg: dict, bus: AgentBus) -> None:
    """Process a patient safety question.

    Message format expected:
        {
          "from": "SomeAgent",
          "data": {
            "question": "Is it safe to prescribe X to patient Y given Z?",
            "task": "optional task description"
          }
        }

    Response sent back:
        bus.send(to=from_agent, action='safety_result',
                 data={"result": "<analysis text>", "vault_path": "<path>"})
    """
    data = msg.get("data", {})
    question = data.get("question", data.get("task", ""))
    from_agent = msg.get("from", "unknown")

    if not question:
        bus.send(
            to=from_agent,
            from_="PatientSafety",
            action="safety_result",
            data={"status": "error", "error": "No question or task field in request"},
        )
        return

    log(f"[Safety] Received safety_request from {from_agent}: {question[:100]}...")

    try:
        # 1. Load safety prompt
        safety_prompt_content = _load_safety_prompt()

        # 2. Build full prompt
        full_prompt = (
            "You are PatientSafety for Aestas Healthcare.\n\n"
            f"{safety_prompt_content}\n\n"
            f"QUESTION: {question}\n\n"
            "Provide patient safety analysis."
        )

        # 3. Call Claude Code
        result_text = _call_claude_code(full_prompt, timeout=180)

        # 4. Strip any markdown fences that may have leaked through
        result_text = _strip_markdown_fences(result_text)

        # 5. Save to vault
        vault_path = _save_to_vault(result_text, question)

        # 6. Send response
        bus.send(
            to=from_agent,
            from_="PatientSafety",
            action="safety_result",
            data={
                "status": "complete",
                "result": result_text,
                "vault_path": vault_path,
                "question": question,
            },
        )
        log(f"[Safety] Completed safety_request from {from_agent}")

    except Exception as e:
        import traceback
        log(f"[Safety] Error processing safety_request: {e}")
        log(f"[Safety] Traceback: {traceback.format_exc()}")
        bus.send(
            to=from_agent,
            from_="PatientSafety",
            action="safety_result",
            data={"status": "error", "error": str(e), "question": question},
        )


def handle_ping(msg: dict, bus: AgentBus) -> None:
    """Respond to a ping with a pong."""
    from_agent = msg.get("from", "unknown")
    log(f"[Ping] Received ping from {from_agent}, sending pong")
    bus.send(to=from_agent, from_="PatientSafety", action="pong", data={"status": "alive"})


# ── Main loop ──────────────────────────────────────────────────────────────────
def main():
    log("[PatientSafety] Daemon starting, listening as 'PatientSafety' on AgentBus...")
    bus = AgentBus()

    def shutdown(signum, frame):
        log("[PatientSafety] Shutting down on signal...")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        try:
            msg = bus.recv(agent_name="PatientSafety", timeout=300)
            if msg is None:
                # Timeout — loop back and keep listening
                continue

            action = msg.get("action", "")
            log(f"[PatientSafety] Received action='{action}' from={msg.get('from', '?')}")

            if action == "safety_request":
                handle_safety_request(msg, bus)
            elif action == "ping":
                handle_ping(msg, bus)
            else:
                log(f"[PatientSafety] Unknown action '{action}', ignoring")

        except KeyboardInterrupt:
            log("[PatientSafety] Interrupted, exiting main loop")
            break
        except Exception as e:
            log(f"[PatientSafety] Unexpected error in main loop: {e}")
            import traceback
            traceback.print_exc()
            continue


if __name__ == "__main__":
    main()
