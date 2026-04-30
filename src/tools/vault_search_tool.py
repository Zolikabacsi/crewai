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