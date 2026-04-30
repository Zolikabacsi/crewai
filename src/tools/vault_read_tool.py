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