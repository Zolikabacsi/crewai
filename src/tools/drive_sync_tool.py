"""Drive sync tool — list Drive folder files and download new ones."""

from crewai.tools import BaseTool
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
