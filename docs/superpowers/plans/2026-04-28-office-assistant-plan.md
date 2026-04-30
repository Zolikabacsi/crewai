# Office Assistant Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `OfficeAssistant` crewAI agent with 5 tools (calendar, email, vault search, vault read, Drive sync) that works in both standalone query mode and as a delegatable crew agent, plus a standalone daily Drive sync script.

**Architecture:** Each tool is a `BaseTool` subclass wrapping `subprocess.run()` calls to `~/bin/gws` (calendar/gmail/drive) or Python stdlib (vault FS). The `OfficeAssistant` agent uses all 5 tools. The daily sync script runs independently via cron, comparing Drive state against a JSON checkpoint file.

**Tech Stack:** crewai, crewai_tools, subprocess, pathlib, json, os, re, datetime, pathlib.Path

---

## File Map

```
srv/crewai/src/
├── tools/
│   ├── __init__.py           # Create: export all 5 tools
│   ├── calendar_tool.py      # Create: CalendarTool via gws
│   ├── email_tool.py         # Create: EmailSearchTool via gws
│   ├── vault_search_tool.py  # Create: VaultSearchTool via FS grep
│   ├── vault_read_tool.py    # Create: VaultReadTool via FS read
│   └── drive_sync_tool.py    # Create: DriveSyncTool via gws
├── agents/
│   ├── __init__.py           # Modify: add OfficeAssistant export
│   └── office_assistant.py   # Create: OfficeAssistant agent + tools
├── tasks/
│   ├── __init__.py           # Modify: add sync_drive_task export
│   └── office_tasks.py       # Create: sync_drive_task

srv/crewai/scripts/
└── daily_sync.py             # Create: standalone sync entry point
```

---

### Task 1: Create `CalendarTool`

**Files:**
- Create: `srv/crewai/src/tools/calendar_tool.py`

```python
"""Calendar tool — uses gws calendar to list events."""

from crewai.tools import BaseTool
from pydantic import Field
import subprocess
import json
from datetime import datetime, timedelta
from typing import Optional


def _run_gws(args: list) -> dict:
    """Run gws command and return parsed JSON."""
    result = subprocess.run(
        ["~/bin/gws"] + args,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return {"error": result.stderr}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw": result.stdout}


class CalendarTool(BaseTool):
    name: str = "CalendarTool"
    description: str = (
        "Use this tool to list calendar events. "
        "Call with action='list' and optionally start_date/end_date (YYYY-MM-DD). "
        "Returns the list of events with title, start time, and attendees."
    )

    def _run(self, action: str = "list", start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
        if action == "list":
            params = {"calendarId": "primary", "timeMin": start_date or "", "timeMax": end_date or ""}
            # Build gws args
            args = ["calendar", "events", "list", "--params", json.dumps(params)]
            result = _run_gws(args)

            if "error" in result:
                return f"Error: {result['error']}"

            events = result.get("events", result.get("items", []))
            if not events:
                return "No events found in the specified range."

            lines = []
            for e in events:
                start = e.get("start", {}).get("dateTime", e.get("start", {}).get("date", "unknown"))
                summary = e.get("summary", "(No title)")
                attendees = e.get("attendees", [])
                lines.append(f"- {start}: {summary} ({len(attendees)} attendees)")
            return "\n".join(lines)

        return "Unknown action. Use action='list'."
```

- [ ] **Step 1: Write the tool file**

Create `srv/crewai/src/tools/calendar_tool.py` with the code above.

- [ ] **Step 2: Verify it imports**

Run: `cd ~/srv/crewai && source .venv/bin/activate && python -c "from src.tools.calendar_tool import CalendarTool; print('OK')"`
Expected: `OK` (no errors)

- [ ] **Step 3: Commit**

```bash
cd ~/srv/crewai
git add src/tools/calendar_tool.py
git commit -m "feat(office): add CalendarTool via gws

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

### Task 2: Create `EmailSearchTool`

**Files:**
- Create: `srv/crewai/src/tools/email_tool.py`

```python
"""Email search tool — uses gws gmail to search and read emails."""

from crewai.tools import BaseTool
from pydantic import Field
import subprocess
import json
from typing import Optional


def _run_gws(args: list) -> dict:
    result = subprocess.run(
        ["~/bin/gws"] + args,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return {"error": result.stderr}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw": result.stdout}


class EmailSearchTool(BaseTool):
    name: str = "EmailSearchTool"
    description: str = (
        "Use this tool to search emails and read email bodies. "
        "action='search': pass query string (e.g. 'from:accountant subject:Q1'). "
        "action='read': pass message_id to get full email content. "
        "Returns matching email summaries or full email body."
    )

    def _run(self, action: str = "search", query: str = "", message_id: str = "") -> str:
        if action == "search":
            params = {"q": query, "maxResults": 10, "userId": "me"}
            result = _run_gws(["gmail", "users", "messages", "list", "--params", json.dumps(params)])
            if "error" in result:
                return f"Error: {result['error']}"

            messages = result.get("messages", [])
            if not messages:
                return "No emails found matching that query."

            # Summarize each message (id + snippet)
            lines = []
            for m in messages[:10]:
                mid = m["id"]
                # Get snippet via get
                detail = _run_gws(["gmail", "users", "messages", "get", "--params", json.dumps({"userId": "me", "id": mid})])
                snippet = detail.get("snippet", "")
                subject = ""
                for h in detail.get("payload", {}).get("headers", []):
                    if h["name"].lower() == "subject":
                        subject = h["value"]
                        break
                lines.append(f"- [{mid}] {subject}: {snippet[:80]}...")
            return "\n".join(lines)

        elif action == "read":
            if not message_id:
                return "Error: message_id required for read action."
            detail = _run_gws(["gmail", "users", "messages", "get", "--params", json.dumps({"userId": "me", "id": message_id})])
            if "error" in detail:
                return f"Error: {detail['error']}"
            snippet = detail.get("snippet", "")
            subject = ""
            from_addr = ""
            for h in detail.get("payload", {}).get("headers", []):
                if h["name"].lower() == "subject":
                    subject = h["value"]
                if h["name"].lower() == "from":
                    from_addr = h["value"]
            body_parts = detail.get("payload", {}).get("body", {})
            text = body_parts.get("data", "")
            if not text:
                # Walk parts
                parts = detail.get("payload", {}).get("parts", [])
                for p in parts:
                    if p.get("mimeType") == "text/plain":
                        text = p.get("body", {}).get("data", "")
                        break
            import base64
            if text:
                text = base64.urlsafe_b64decode(text.encode()).decode()
            return f"From: {from_addr}\nSubject: {subject}\n\n{text or snippet}"

        return "Unknown action. Use action='search' or action='read'."
```

- [ ] **Step 1: Write the tool file**

Create `srv/crewai/src/tools/email_tool.py` with the code above.

- [ ] **Step 2: Verify it imports**

Run: `cd ~/srv/crewai && source .venv/bin/activate && python -c "from src.tools.email_tool import EmailSearchTool; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd ~/srv/crewai
git add src/tools/email_tool.py
git commit -m "feat(office): add EmailSearchTool via gws

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

### Task 3: Create `VaultSearchTool` and `VaultReadTool`

**Files:**
- Create: `srv/crewai/src/tools/vault_search_tool.py`
- Create: `srv/crewai/src/tools/vault_read_tool.py`

```python
"""Vault search tool — full-text search across vault files."""

from crewai.tools import BaseTool
from pathlib import Path
import re

VAULT_ROOT = Path.home() / "srv" / "vault"


class VaultSearchTool(BaseTool):
    name: str = "VaultSearchTool"
    description: str = (
        "Use this tool to search across all vault files. "
        "Pass a query string and optionally a vault name ('Aestas Vault' or 'Second Brain'). "
        "Searches file names and content. Returns matching file paths and line context."
    )

    def _run(self, query: str = "", vault: str = "Aestas Vault") -> str:
        vault_path = VAULT_ROOT / vault
        if not vault_path.exists():
            return f"Vault not found: {vault_path}"

        results = []
        for md_file in vault_path.rglob("*.md"):
            try:
                content = md_file.read_text(errors="ignore")
                if query.lower() in content.lower():
                    # Find context lines
                    lines = content.split("\n")
                    matches = [f"  {i+1}: {l}" for i, l in enumerate(lines) if query.lower() in l.lower()]
                    results.append(f"{md_file.relative_to(vault_path)}:\n" + "\n".join(matches[:3]))
            except Exception:
                continue

        if not results:
            return f"No results found for '{query}' in {vault}"
        return "\n---\n".join(results[:20])
```

```python
"""Vault read tool — read specific document content."""

from crewai.tools import BaseTool
from pathlib import Path

VAULT_ROOT = Path.home() / "srv" / "vault"


class VaultReadTool(BaseTool):
    name: str = "VaultReadTool"
    description: str = (
        "Use this tool to read the full content of a specific vault file. "
        "Pass the relative path within the vault (e.g. 'Accountant/Q1_report.pdf' or 'wiki/sources/doc.md'). "
        "Returns the file content (text) or a note if binary."
    )

    def _run(self, relative_path: str = "", vault: str = "Aestas Vault") -> str:
        vault_path = VAULT_ROOT / vault
        file_path = vault_path / relative_path

        if not file_path.exists():
            return f"File not found: {relative_path} in {vault}"

        if file_path.suffix.lower() in [".pdf", ".png", ".jpg", ".jpeg", ".gif", ".zip"]:
            return f"[Binary file: {file_path.name}] — content not displayed"

        try:
            content = file_path.read_text(errors="ignore")
            return content[:3000]  # Truncate at 3000 chars
        except Exception as e:
            return f"Error reading file: {e}"
```

- [ ] **Step 1: Write vault_search_tool.py**

- [ ] **Step 2: Write vault_read_tool.py**

- [ ] **Step 3: Verify both import**

Run: `cd ~/srv/crewai && source .venv/bin/activate && python -c "from src.tools.vault_search_tool import VaultSearchTool; from src.tools.vault_read_tool import VaultReadTool; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd ~/srv/crewai
git add src/tools/vault_search_tool.py src/tools/vault_read_tool.py
git commit -m "feat(office): add VaultSearchTool and VaultReadTool

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

### Task 4: Create `DriveSyncTool`

**Files:**
- Create: `srv/crewai/src/tools/drive_sync_tool.py`

```python
"""Drive sync tool — list Drive folder files and download new ones."""

from crewai.tools import BaseTool
from crewai_tools import BaseTool
from pydantic import Field
import subprocess
import json
from pathlib import Path
from typing import Optional

VAULT_ROOT = Path.home() / "srv" / "vault"
SYNC_STATE_FILE = Path.home() / ".claude" / "office_assistant_last_sync.json"
DRIVE_FOLDER = "Aestas Group/Aestras Healthcare Ltd"


def _run_gws(args: list) -> dict:
    result = subprocess.run(
        ["~/bin/gws"] + args,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return {"error": result.stderr}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw": result.stdout}


def _get_or_create_state() -> dict:
    SYNC_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SYNC_STATE_FILE.exists():
        return json.loads(SYNC_STATE_FILE.read_text())
    return {"known_files": {}, "last_run": ""}


class DriveSyncTool(BaseTool):
    name: str = "DriveSyncTool"
    description: str = (
        "Use this tool to list files in the monitored Drive folder "
        "(Aestas Group/Aestras Healthcare Ltd) or check for new files. "
        "action='list': returns file list. "
        "action='sync': compares to last run and returns new file IDs. "
        "Use action='sync' to find newly added files that need ingesting."
    )

    def _run(self, action: str = "list", vault: str = "Aestas Vault") -> str:
        # First find the folder ID
        folder_result = _run_gws(["drive", "files", "list", "--params", json.dumps({
            "q": f"name='Aestas Healthcare Ltd' and mimeType='application/vnd.google-apps.folder'",
            "pageSize": 5,
        })])
        if "error" in folder_result:
            return f"Error finding folder: {folder_result['error']}"

        folders = folder_result.get("files", [])
        if not folders:
            return "Drive folder 'Aestas Healthcare Ltd' not found."

        folder_id = folders[0]["id"]

        # List files in this folder
        files_result = _run_gws(["drive", "files", "list", "--params", json.dumps({
            "q": f"'{folder_id}' in parents and trashed=false",
            "pageSize": 100,
        })])
        if "error" in files_result:
            return f"Error listing files: {files_result['error']}"

        files = files_result.get("files", [])
        if action == "list":
            if not files:
                return "No files found in Drive folder."
            lines = [f"- {f['name']} ({f.get('mimeType', 'unknown')})" for f in files]
            return "\n".join(lines)

        elif action == "sync":
            state = _get_or_create_state()
            known = set(state.get("known_files", {}).keys())
            current = {f["id"]: f["name"] for f in files}
            new_ids = set(current.keys()) - known

            if not new_ids:
                return "No new files found."

            new_files = [{"id": fid, "name": current[fid]} for fid in new_ids]
            return json.dumps(new_files, indent=2)

        return "Unknown action. Use action='list' or action='sync'."
```

- [ ] **Step 1: Write the tool file**

- [ ] **Step 2: Verify it imports**

Run: `cd ~/srv/crewai && source .venv/bin/activate && python -c "from src.tools.drive_sync_tool import DriveSyncTool; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd ~/srv/crewai
git add src/tools/drive_sync_tool.py
git commit -m "feat(office): add DriveSyncTool via gws

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

### Task 5: Create `tools/__init__.py`

**Files:**
- Create: `srv/crewai/src/tools/__init__.py`

```python
"""Office tools — calendar, email, vault, and drive."""

from .calendar_tool import CalendarTool
from .email_tool import EmailSearchTool
from .vault_search_tool import VaultSearchTool
from .vault_read_tool import VaultReadTool
from .drive_sync_tool import DriveSyncTool

__all__ = [
    "CalendarTool",
    "EmailSearchTool",
    "VaultSearchTool",
    "VaultReadTool",
    "DriveSyncTool",
]
```

- [ ] **Step 1: Write `__init__.py`**

- [ ] **Step 2: Verify all tools export**

Run: `cd ~/srv/crewai && source .venv/bin/activate && python -c "from src.tools import CalendarTool, EmailSearchTool, VaultSearchTool, VaultReadTool, DriveSyncTool; print('All tools OK')"`
Expected: `All tools OK`

- [ ] **Step 3: Commit**

```bash
cd ~/srv/crewai
git add src/tools/__init__.py
git commit -m "feat(office): add tools __init__.py with all 5 tools

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

### Task 6: Create `OfficeAssistant` agent

**Files:**
- Create: `srv/crewai/src/agents/office_assistant.py`

```python
"""Office Assistant agent — calendar, email, vault, Drive sync."""

from crewai import Agent
from crewai.llm import LLM
from ..config import Config
from ..tools import (
    CalendarTool,
    EmailSearchTool,
    VaultSearchTool,
    VaultReadTool,
    DriveSyncTool,
)


def get_llm():
    return LLM(
        provider="anthropic",
        model="MiniMax-M2.7",
        api_key=Config.ANTHROPIC_AUTH_TOKEN,
        base_url=Config.ANTHROPIC_BASE_URL,
    )


class OfficeAssistant(Agent):
    def __init__(self):
        super().__init__(
            role="Office & Calendar Assistant",
            goal=(
                "Provide accurate, real-time answers about your schedule, "
                "email context, and company documents. Maintain vault sync with Drive."
            ),
            backstory=(
                "You are a diligent executive assistant with access to Google Calendar, "
                "Gmail, and the company document vault. You answer questions precisely, "
                "maintain strict privacy, and run a daily check to keep the vault up to "
                "date with new Drive files."
            ),
            verbose=Config.VERBOSE,
            tools=[
                CalendarTool(),
                EmailSearchTool(),
                VaultSearchTool(),
                VaultReadTool(),
                DriveSyncTool(),
            ],
            llm=get_llm(),
        )
```

- [ ] **Step 1: Write the agent file**

- [ ] **Step 2: Verify it imports**

Run: `cd ~/srv/crewai && source .venv/bin/activate && python -c "from src.agents.office_assistant import OfficeAssistant; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd ~/srv/crewai
git add src/agents/office_assistant.py
git commit -m "feat(office): add OfficeAssistant agent with 5 tools

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

### Task 7: Update agents `__init__.py`

**Files:**
- Modify: `srv/crewai/src/agents/__init__.py`

```python
from .agents import get_all_agents, MarketResearcher, FinancialAnalyst, RiskAssessor, BusinessWriter
from .office_assistant import OfficeAssistant

__all__ = [
    "get_all_agents",
    "MarketResearcher",
    "FinancialAnalyst",
    "RiskAssessor",
    "BusinessWriter",
    "OfficeAssistant",
]
```

- [ ] **Step 1: Update `__init__.py`**

- [ ] **Step 2: Verify export**

Run: `cd ~/srv/crewai && source .venv/bin/activate && python -c "from src.agents import OfficeAssistant; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd ~/srv/crewai
git add src/agents/__init__.py
git commit -m "feat(office): export OfficeAssistant from agents module

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

### Task 8: Create `office_tasks.py` and update tasks `__init__.py`

**Files:**
- Create: `srv/crewai/src/tasks/office_tasks.py`
- Modify: `srv/crewai/src/tasks/__init__.py`

```python
"""Office task definitions."""

from crewai import Task
from ..agents.office_assistant import OfficeAssistant


def sync_drive_task(context: list = None) -> Task:
    """Daily Drive sync task — check for new files and ingest into vault.

    Args:
        context: Optional list of previous task outputs for context.

    Returns:
        Configured Task instance.
    """
    return Task(
        description=(
            "Check for new files in the Drive folder 'Aestas Group/Aestras Healthcare Ltd'. "
            "Use the DriveSyncTool with action='sync' to identify new files since last run. "
            "For each new file:\n"
            "1. Download it to ~/srv/vault/Aestas Vault/raw/\n"
            "2. Create wiki/sources/[name].md summary in Aestas Vault\n"
            "3. Update meta/index.md catalog\n"
            "4. Append to meta/log.md\n\n"
            "Use VaultReadTool to read new files before creating summaries."
        ),
        agent=OfficeAssistant(),
        expected_output=(
            "A report of new files synced, including downloaded file paths "
            "and a list of vault wiki entries created or updated."
        ),
        context=context,
    )
```

Update `srv/crewai/src/tasks/__init__.py`:

```python
from .tasks import (
    market_research_task,
    financial_analysis_task,
    risk_assessment_task,
    report_writing_task,
)
from .office_tasks import sync_drive_task

__all__ = [
    "market_research_task",
    "financial_analysis_task",
    "risk_assessment_task",
    "report_writing_task",
    "sync_drive_task",
]
```

- [ ] **Step 1: Create `office_tasks.py`**

- [ ] **Step 2: Update tasks `__init__.py`**

- [ ] **Step 3: Verify imports**

Run: `cd ~/srv/crewai && source .venv/bin/activate && python -c "from src.tasks import sync_drive_task; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd ~/srv/crewai
git add src/tasks/office_tasks.py src/tasks/__init__.py
git commit -m "feat(office): add sync_drive_task and export from tasks module

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

### Task 9: Create `scripts/daily_sync.py`

**Files:**
- Create: `srv/crewai/scripts/daily_sync.py`

```python
#!/usr/bin/env python3
"""Daily Drive sync script — run via cron.

Compares Drive folder state against last known state,
downloads new files, and runs the vault ingest workflow.
"""

import subprocess
import json
import sys
from pathlib import Path
from datetime import datetime

VAULT_ROOT = Path.home() / "srv" / "vault"
AESTAS_RAW = VAULT_ROOT / "Aestas Vault" / "raw"
SYNC_STATE = Path.home() / ".claude" / "office_assistant_last_sync.json"
DRIVE_FOLDER_NAME = "Aestas Healthcare Ltd"


def run_gws(args: list) -> dict:
    result = subprocess.run(
        ["~/bin/gws"] + args,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return {"error": result.stderr}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw": result.stdout}


def get_folder_id(name: str) -> str | None:
    result = run_gws(["drive", "files", "list", "--params", json.dumps({
        "q": f"name='{name}' and mimeType='application/vnd.google-apps.folder'",
        "pageSize": 5,
    })])
    files = result.get("files", [])
    return files[0]["id"] if files else None


def list_folder_files(folder_id: str) -> list:
    result = run_gws(["drive", "files", "list", "--params", json.dumps({
        "q": f"'{folder_id}' in parents and trashed=false",
        "pageSize": 200,
    })])
    return result.get("files", [])


def download_file(file_id: str, name: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / name
    # Replace unsafe chars in filename
    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in name)
    out_path = dest_dir / safe_name

    result = subprocess.run(
        ["~/bin/gws", "drive", "files", "get",
         "--params", json.dumps({"fileId": file_id}),
         "-o", str(out_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return out_path


def ingest_file(file_path: Path) -> None:
    """Run ingest workflow: create wiki/sources summary, update index/log."""
    vault_root = VAULT_ROOT / "Aestas Vault"
    name = file_path.stem
    source_path = vault_root / "wiki" / "sources" / f"{name}.md"

    content = ""
    if file_path.suffix.lower() == ".md":
        content = file_path.read_text()[:500]
    else:
        content = f"[File: {file_path.name}]"

    summary_content = f"""---
title: {file_path.name}
type: source
tags: [drive-sync]
created: {datetime.now().strftime('%Y-%m-%d')}
updated: {datetime.now().strftime('%Y-%m-%d')}
sources: [{file_path.name}]
---

Auto-ingested from Drive on {datetime.now().strftime('%Y-%m-%d')}.

{content[:300]}
"""

    source_path.write_text(summary_content)

    # Update meta/index.md
    index_path = vault_root / "meta" / "index.md"
    entry = f"\n- [wiki/sources/{name}.md](wiki/sources/{name}.md) | drive-sync | {datetime.now().strftime('%Y-%m-%d')}"
    if index_path.exists():
        index_path.write_text(index_path.read_text() + entry)
    else:
        index_path.write_text(f"# Index\n{entry}\n")

    # Append to meta/log.md
    log_path = vault_root / "meta" / "log.md"
    log_entry = f"\n## [{datetime.now().strftime('%Y-%m-%d')}] ingest | {file_path.name}"
    if log_path.exists():
        log_path.write_text(log_path.read_text() + log_entry)
    else:
        log_path.write_text(f"# Log\n{log_entry}\n")

    print(f"  Ingested: {file_path.name} -> wiki/sources/{name}.md")


def main():
    print("=== Office Assistant Daily Sync ===")
    print(f"Time: {datetime.now().isoformat()}")

    folder_id = get_folder_id(DRIVE_FOLDER_NAME)
    if not folder_id:
        print(f"ERROR: Folder '{DRIVE_FOLDER_NAME}' not found in Drive")
        sys.exit(1)

    files = list_folder_files(folder_id)
    print(f"Found {len(files)} files in Drive folder")

    # Load previous state
    SYNC_STATE.parent.mkdir(parents=True, exist_ok=True)
    if SYNC_STATE.exists():
        state = json.loads(SYNC_STATE.read_text())
        known_ids = set(state.get("known_ids", []))
    else:
        known_ids = set()

    current_ids = {f["id"] for f in files}
    new_ids = current_ids - known_ids

    if not new_ids:
        print("No new files. Sync complete.")
        state = {"known_ids": list(current_ids), "last_run": datetime.now().isoformat()}
        SYNC_STATE.write_text(json.dumps(state, indent=2))
        return

    print(f"Found {len(new_ids)} new file(s):")
    for f in files:
        if f["id"] in new_ids:
            print(f"  - {f['name']}")

    for f in files:
        if f["id"] not in new_ids:
            continue
        file_path = download_file(f["id"], f["name"], AESTAS_RAW)
        print(f"  Downloaded: {file_path}")
        ingest_file(file_path)

    state = {"known_ids": list(current_ids), "last_run": datetime.now().isoformat()}
    SYNC_STATE.write_text(json.dumps(state, indent=2))
    print("Sync complete.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 1: Create `scripts/` directory and `daily_sync.py`**

```bash
mkdir -p ~/srv/crewai/scripts
```

- [ ] **Step 2: Write `daily_sync.py`**

- [ ] **Step 3: Make it executable and verify it parses**

Run: `chmod +x ~/srv/crewai/scripts/daily_sync.py && cd ~/srv/crewai && source .venv/bin/activate && python -c "import scripts.daily_sync; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd ~/srv/crewai
git add scripts/daily_sync.py
git commit -m "feat(office): add daily_sync.py script for Drive sync

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

### Task 10: Schedule the daily sync via cron

**Files:**
- Modify: `.claude/scheduled_tasks.json`

- [ ] **Step 1: Schedule cron job**

Run: Use the `CronCreate` tool to create a daily recurring task:
- cron: `"0 8 * * *"`
- prompt: `"cd ~/srv/crewai && source .venv/bin/activate && python scripts/daily_sync.py"`
- durable: `true`
- recurring: `true`
- reason: `"Daily Drive sync to vault — pulls new files from Aestas Group/Aestras Healthcare Ltd and runs ingest workflow"`

- [ ] **Step 2: Commit the change**

```bash
cd ~/srv/crewai
git add .
git commit -m "chore(office): schedule daily Drive sync cron job

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| CalendarTool via gws | Task 1 |
| EmailSearchTool via gws | Task 2 |
| VaultSearchTool via FS | Task 3 |
| VaultReadTool via FS | Task 3 |
| DriveSyncTool via gws | Task 4 |
| OfficeAssistant agent with all 5 tools | Tasks 5, 6 |
| Add to agents/__init__.py | Task 7 |
| sync_drive_task | Task 8 |
| Daily sync script | Task 9 |
| Cron schedule | Task 10 |

**No gaps found.**

## Placeholder Scan

All steps have complete code. No "TBD", "TODO", or placeholder descriptions found.

## Type Consistency

All file paths use `Path` consistently. `SYNC_STATE` path is `Path.home() / ".claude" / "office_assistant_last_sync.json"` across drive_sync_tool.py and daily_sync.py. `VAULT_ROOT` defaults to `Path.home() / "srv" / "vault"` consistently.