#!/usr/bin/env python3
"""agent_log_cleanup — nightly cleanup of agent task run logs.

Runs: daily at 03:00 UTC via cron.

Logic:
  • *_success.json  older than 7 days  → extract summary → inject into Hermes memory → delete
  • *_success.json  within 7 days      → keep (still warm)
  • *_failed.json / *_timeout.json / *_interrupted.json → keep forever (diagnostic)

Output:
  ~/srv/logs/cleanup.log  — timestamped action log
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

LOGS_ROOT    = Path("/home/zoltan/srv/logs")
CLEANUP_LOG = LOGS_ROOT / "cleanup.log"
RETENTION_DAYS = 7   # success logs older than this → summarise + delete

# Success statuses that are eligible for cleanup
CLEANABLE_STATUSES = {"success"}
# Failure statuses that are kept forever
FOREVER_STATUSES    = {"failed", "timeout", "interrupted", "cancelled"}
# All statuses
ALL_STATUSES = CLEANABLE_STATUSES | FOREVER_STATUSES

# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def clog(action: str, detail: str) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    line = f"{ts} | {action:<20} | {detail}"
    print(line)
    CLEANUP_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CLEANUP_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------------------
# Hermes memory injection
# ---------------------------------------------------------------------------

def inject_to_memory(summary: str, agent: str, task_name: str,
                     duration_s: float | None, vault_path: str | None,
                     status: str) -> bool:
    """Write a task summary to a pending memory file.

    The cron agent reads pending_memory.jsonl after cleanup and uses the Hermes
    memory tool to inject entries. This avoids subprocess complexity here.
    """
    pending = Path.home() / ".hermes" / "pending_memory.jsonl"
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "text": (
            f"Agent: {agent} | Task: {task_name} | "
            f"Duration: {f'{duration_s:.0f}s' if duration_s else 'unknown'} | "
            f"Status: {status}"
            + (f" | Vault: {vault_path}" if vault_path else "")
            + f" | Summary: {summary}"
        ),
        "agent": agent,
        "task_name": task_name,
        "status": status,
    }
    try:
        pending.parent.mkdir(parents=True, exist_ok=True)
        with open(pending, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Core cleanup logic
# ---------------------------------------------------------------------------

def get_status_from_filename(filename: str) -> str | None:
    """Extract status from *_status.json filename."""
    for s in ALL_STATUSES:
        if filename.endswith(f"_{s}.json"):
            return s
    return None


def is_older_than(path: Path, days: int) -> bool:
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return datetime.now(timezone.utc) - mtime > timedelta(days=days)
    except OSError:
        return False


def cleanup_agent(agent: str) -> tuple[int, int, int]:
    """Clean one agent's runs directory.

    Returns: (cleaned_count, kept_count, error_count)
    """
    runs_dir = LOGS_ROOT / agent / "runs"
    if not runs_dir.exists():
        return 0, 0, 0

    cleaned = kept = errors = 0

    for log_file in runs_dir.glob("*.json"):
        status = get_status_from_filename(log_file.name)
        if status is None:
            clog("SKIP_UNKNOWN_STATUS", f"{log_file.name} — status unknown, skipping")
            continue

        try:
            with open(log_file, encoding="utf-8") as f:
                data = json.load(f)

            summary   = data.get("summary") or f"Task: {data.get('task_name','?')} | Status: {status}"
            duration  = data.get("duration_s")
            vault     = data.get("vault_output_path")
            task_name = data.get("task_name", log_file.stem)

            if status in CLEANABLE_STATUSES and is_older_than(log_file, RETENTION_DAYS):
                # Inject to memory first
                mem_ok = inject_to_memory(summary, agent, task_name, duration, vault, status)
                mem_note = "memory_injected" if mem_ok else "memory_inject_failed"

                log_file.unlink()
                cleaned += 1
                clog("CLEANED", f"{agent}/{log_file.name} | {mem_note}")

            elif status in FOREVER_STATUSES:
                kept += 1
                clog("KEPT_FOREVER", f"{agent}/{log_file.name} | status={status}")

            else:  # success but within retention window
                kept += 1
                clog("KEPT_WARM", f"{agent}/{log_file.name} | within {RETENTION_DAYS}-day window")

        except Exception as e:
            errors += 1
            clog("ERROR", f"{agent}/{log_file.name} — {e}: {traceback.format_exc()[:200]}")

    return cleaned, kept, errors


def main():
    clog("START", f"Cleanup run started | retention={RETENTION_DAYS} days | root={LOGS_ROOT}")

    total_cleaned = total_kept = total_errors = 0

    if not LOGS_ROOT.exists():
        clog("EMPTY", f"Logs root does not exist: {LOGS_ROOT}")
        return

    # Process each agent subdirectory
    for agent_dir in sorted(LOGS_ROOT.iterdir()):
        if not agent_dir.is_dir() or agent_dir.name == "cleanup.log":
            continue
        clog("AGENT", f"Processing agent: {agent_dir.name}")
        c, k, e = cleanup_agent(agent_dir.name)
        total_cleaned += c
        total_kept    += k
        total_errors  += e

    clog("SUMMARY",
         f"cleaned={total_cleaned} | kept={total_kept} | errors={total_errors}")
    clog("DONE", "Cleanup run complete")

    # Print for cron output capture
    print(f"\nCleanup complete: cleaned={total_cleaned}, kept={total_kept}, errors={total_errors}")


if __name__ == "__main__":
    main()
