#!/usr/bin/env python3
"""Daily Drive sync script — run via cron.

Compares Drive folder state against last known state,
downloads new files, and runs the vault ingest workflow.
"""

import subprocess
import json
import sys
import os
from pathlib import Path
from datetime import datetime

VAULT_ROOT = Path.home() / "srv" / "vault"
AESTAS_RAW = VAULT_ROOT / "Aestas Vault" / "raw"
SYNC_STATE = Path.home() / ".claude" / "office_assistant_last_sync.json"
DRIVE_FOLDER_NAME = "Aestas Healthcare Ltd"


def run_gws(args: list) -> dict:
    result = subprocess.run(
        [os.path.expanduser("~/bin/gws")] + args,
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
    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in name)
    out_path = dest_dir / safe_name

    result = subprocess.run(
        [os.path.expanduser("~/bin/gws"), "drive", "files", "get",
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

    index_path = vault_root / "meta" / "index.md"
    entry = f"\n- [wiki/sources/{name}.md](wiki/sources/{name}.md) | drive-sync | {datetime.now().strftime('%Y-%m-%d')}"
    if index_path.exists():
        index_path.write_text(index_path.read_text() + entry)
    else:
        index_path.write_text(f"# Index\n{entry}\n")

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
