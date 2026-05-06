"""agent_logger — structured task-run logging for all Aestas agents.

Two distinct products:
  ① Task Run Log  — ~/srv/logs/{agent}/runs/YYYY-MM-DD_{slug}_{status}.json
                    Steps, tool calls, errors, timing. Consumed by cron cleanup.
                    Retention: success → 7 days then summary→memory then delete;
                              failed/timeout/interrupted → kept forever.

  ② Generated Artefact — lands in Second Brain vault under Aestas_{Agent}/.
                    Content output. Consumed by wiki ingestion. Permanent.

Usage (context manager):
    from src.agent_logger import AgentLogger

    with AgentLogger(agent="cmo", task_name="brand_strategy", vault_output_path=path) as log:
        log.step("receive_task", {"task": task})
        result = run_marketing_campaign(task)
        log.step("crew_complete", {"result_type": type(result).__name__})
        log.capture_output(result)          # writes artefact
        log.finish(status="success", summary="Brand strategy generated in 3m42s")
"""

from __future__ import annotations

import json
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

STATUSES = {"success", "failed", "timeout", "interrupted", "cancelled"}


@dataclass
class Step:
    label: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_ms: float | None = None
    data: dict[str, Any] | None = None


@dataclass
class TaskRunLog:
    log_id: str
    agent: str
    task_name: str
    slug: str
    status: str  # success | failed | timeout | interrupted | cancelled
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None
    duration_s: float | None = None
    steps: list[Step] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    vault_output_path: str | None = None
    summary: str | None = None
    token_usage: dict | None = None  # reserved for future

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# Main logger class
# ---------------------------------------------------------------------------

class AgentLogger:
    """
    Context manager that wraps an agent task run with structured logging.

    Args:
        agent:        Agent name, used as subfolder name (e.g. "cmo", "cfo")
        task_name:    Human-readable task description (e.g. "brand_strategy")
        vault_output_path: Path where the generated artefact was saved (optional)
        retention_days: Days before a 'success' log is eligible for cleanup (default 7)
    """

    LOGS_ROOT = Path("/home/zoltan/srv/logs")

    def __init__(
        self,
        agent: str,
        task_name: str,
        vault_output_path: str | None = None,
        retention_days: int = 7,
    ):
        self.agent = agent.lower().strip()
        self.task_name = task_name.strip()
        self.vault_output_path = vault_output_path
        self.retention_days = retention_days
        self._step_start: datetime | None = None
        self._run: TaskRunLog | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def step(self, label: str, data: dict[str, Any] | None = None) -> None:
        """Record a named step with optional structured data."""
        if self._run is None:
            return
        duration_ms = None
        if self._step_start is not None:
            duration_ms = (datetime.now(timezone.utc) - self._step_start).total_seconds() * 1000
        self._run.steps.append(Step(label=label, duration_ms=duration_ms, data=data))
        self._step_start = datetime.now(timezone.utc)

    def error(self, exc: BaseException | str, traceback_str: str | None = None) -> None:
        """Record an error with optional traceback."""
        if self._run is None:
            return
        if isinstance(exc, str):
            self._run.errors.append({
                "type": "string",
                "message": exc,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        else:
            self._run.errors.append({
                "type": exc.__class__.__name__,
                "message": str(exc),
                "traceback": traceback_str or traceback.format_exc(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    def capture_output(self, output: Any, vault_path: str | None = None) -> None:
        """Store the generated artefact path for the log record."""
        self.vault_output_path = vault_path or self.vault_output_path
        self.step("output_captured", {
            "vault_path": self.vault_output_path,
            "output_type": type(output).__name__,
        })

    def finish(
        self,
        status: str,
        summary: str | None = None,
        vault_path: str | None = None,
    ) -> None:
        """Mark the run as complete with given status and summary."""
        if self._run is None:
            return
        if status not in STATUSES:
            raise ValueError(f"Unknown status '{status}'. Must be one of {STATUSES}")
        self._run.status = status
        self._run.summary = summary
        if vault_path:
            self._run.vault_output_path = vault_path
        self._flush()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "AgentLogger":
        ts = datetime.now(timezone.utc)
        log_id = str(uuid.uuid4())[:8]
        slug = _slugify(self.task_name)
        self._run = TaskRunLog(
            log_id=log_id,
            agent=self.agent,
            task_name=self.task_name,
            slug=slug,
            status="interrupted",  # will be overwritten on finish()
        )
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._step_start = ts
        self.step("run_start", {
            "log_id": log_id,
            "retention_days": self.retention_days,
            "vault_root": str(self.vault_output_path) if self.vault_output_path else None,
        })
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._run is None:
            return
        if exc_type is not None:
            status = "failed"
            if exc_type.__name__ == "TimeoutError":
                status = "timeout"
            self.error(exc_val, traceback.format_exc() if exc_tb else None)
            self._run.status = status
        self._flush()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @property
    def _runs_dir(self) -> Path:
        return self.LOGS_ROOT / self.agent / "runs"

    @property
    def _log_file(self) -> Path:
        ts = datetime.now(timezone.utc)
        date_str = ts.strftime("%Y-%m-%d")
        status = self._run.status if self._run else "unknown"
        filename = f"{date_str}_{self._run.slug}_{status}.json"
        return self._runs_dir / filename

    def _flush(self) -> None:
        """Write current run state to disk."""
        if self._run is None:
            return
        self._run.finished_at = datetime.now(timezone.utc).isoformat()
        if self._run.started_at and self._run.finished_at:
            start = datetime.fromisoformat(self._run.started_at)
            end = datetime.fromisoformat(self._run.finished_at)
            self._run.duration_s = (end - start).total_seconds()
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_file, "w", encoding="utf-8") as f:
            json.dump(self._run.to_dict(), f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Turn a task name into a safe filename slug."""
    import re
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s\-_]", "", text)
    text = re.sub(r"[\s]+", "_", text)
    return text[:60]


# ---------------------------------------------------------------------------
# Summary reader — used by cleanup cron
# ---------------------------------------------------------------------------

def read_run_log(log_path: Path) -> TaskRunLog | None:
    """Read a run log JSON back into a TaskRunLog."""
    try:
        with open(log_path, encoding="utf-8") as f:
            d = json.load(f)
        return TaskRunLog(**d)
    except Exception:
        return None


def iter_run_logs(agent: str) -> list[Path]:
    """Return all run log JSON files for an agent, sorted newest first."""
    root = Path("/home/zoltan/srv/logs") / agent / "runs"
    if not root.exists():
        return []
    return sorted(root.glob("*.json"), key=lambda p: p.name, reverse=True)
