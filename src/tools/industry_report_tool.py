"""Industry report tool — search and read reports from the vault."""

from typing import ClassVar

from crewai.tools import BaseTool
from pathlib import Path
import json

VAULT_ROOT = Path.home() / "srv" / "vault"


class IndustryReportTool(BaseTool):
    name: str = "IndustryReportTool"
    description: str = (
        "Use this tool to search industry reports and documents in the vault. "
        "Pass a query string to search across all vault documents. "
        "Pass vault='Aestas Vault' or vault='Second Brain'. "
        "Returns matching document excerpts and paths."
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
                    rel = md_file.relative_to(vault_path)
                    # Extract context around match
                    lines = content.split("\n")
                    matches = [l.strip() for l in lines if query.lower() in l.lower()][:3]
                    results.append(f"**{rel}**\n" + "\n".join(f"  {m}" for m in matches))
            except Exception:
                continue

        if not results:
            return f"No results for '{query}' in {vault}"
        return "\n---\n".join(results[:10])


class OpportunityStorageTool(BaseTool):
    name: str = "OpportunityStorageTool"
    description: str = (
        "Use this tool to store or retrieve side hustle opportunities. "
        "action='save': pass an opportunity dict with title, description, scores, source. "
        "action='list': returns all stored opportunities as JSON. "
        "action='get': pass opportunity_id to get single record."
    )

    STORE_PATH: ClassVar = Path.home() / ".claude" / "side_hustle_opportunities.json"

    def _run(self, action: str = "list", opportunity_id: str = "", data: str = "") -> str:
        self.STORE_PATH.parent.mkdir(parents=True, exist_ok=True)

        if action == "list":
            if not self.STORE_PATH.exists():
                return "[]"
            return self.STORE_PATH.read_text()

        elif action == "save":
            import uuid
            from datetime import datetime
            record = json.loads(data) if data.startswith("{") or data.startswith("[") else {"title": data}
            record["id"] = str(uuid.uuid4())
            record["discovered_date"] = datetime.now().strftime("%Y-%m-%d")
            record["status"] = "pending"

            existing = []
            if self.STORE_PATH.exists():
                try:
                    existing = json.loads(self.STORE_PATH.read_text())
                except Exception:
                    existing = []

            existing.append(record)
            self.STORE_PATH.write_text(json.dumps(existing, indent=2))
            return f"Saved: {record['id']}"

        elif action == "get":
            if not self.STORE_PATH.exists():
                return "Not found"
            try:
                existing = json.loads(self.STORE_PATH.read_text())
                for r in existing:
                    if r.get("id") == opportunity_id:
                        return json.dumps(r, indent=2)
            except Exception:
                pass
            return "Not found"

        return "Unknown action. Use action='list', 'save', or 'get'."