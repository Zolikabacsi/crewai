"""VaultStorageTool — crewAI tool for saving agent outputs to the vault folder structure.

Saves documents to: VAULT_ROOT / agent_folder / sub_folder / {timestamp}_{title}.md
Where VAULT_ROOT = ~/srv/vault/Second Brain/raw
"""

from crewai.tools import BaseTool
from typing import Optional
from pathlib import Path
from datetime import datetime

VAULT_ROOT = Path.home() / "srv" / "vault" / "Second Brain" / "raw"


class VaultStorageTool(BaseTool):
    """Saves documents and analyses to the vault folder structure.

    Use this tool to permanently store any document, analysis, or strategic output
    the agent creates. Documents are saved with YAML frontmatter containing metadata.

    Override agent_folder and sub_folder for each agent type:
    - CFO agents: agent_folder="Aestas_CFO", sub_folder="analyses"
    - CTO agents: agent_folder="Aestas_CTO", sub_folder="tech_decisions"
    - COO agents: agent_folder="Aestas_COO", sub_folder="operational_docs"
    - CMO agents: agent_folder="Aestas_CMO", sub_folder="campaigns"
    """

    name: str = "Vault Document Storage"
    description: str = (
        "Saves documents and analyses to the vault folder structure. "
        "Use this to permanently store any document, analysis, or strategic output "
        "the agent creates. "
        "Input should be a JSON string with keys: content (markdown), title (string), "
        "and optional metadata (dict with agent, doc_type, tags)."
    )

    agent_folder: str = ""  # Override per-agent: "Aestas_CFO", "Aestas_CMO", etc.
    sub_folder: str = ""    # Override per-agent: "analyses", "seo_briefs", etc.

    def _run(self, content: str, title: str, metadata: Optional[dict] = None) -> str:
        """Save content to vault folder.

        Args:
            content: The document content to save (markdown)
            title: Short descriptive title for the document
            metadata: Optional dict with keys: agent, doc_type, tags
        """
        # Determine folder from metadata or instance defaults
        agent = metadata.get("agent", self.agent_folder) if metadata else self.agent_folder
        sub = metadata.get("doc_type", self.sub_folder) if metadata else self.sub_folder

        # Fall back to instance defaults if still empty
        agent = agent or self.agent_folder or "Unknown_Agent"
        sub = sub or self.sub_folder or "general"

        folder = VAULT_ROOT / agent / sub
        folder.mkdir(parents=True, exist_ok=True)

        # Create slug for filename
        slug = title.lower().replace(" ", "_").replace("/", "-").replace("\\", "-")[:50]
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug}.md"
        path = folder / filename

        # Build tags string for frontmatter
        tags_list = metadata.get("tags", []) if metadata else []
        tags_str = ", ".join(tags_list) if tags_list else ""

        # Write with frontmatter header
        frontmatter = f"""---
title: {title}
agent: {agent}
doc_type: {sub}
timestamp: {datetime.now().isoformat()}
tags: [{tags_str}]
---

"""
        path.write_text(frontmatter + content, encoding="utf-8")
        return f"Saved: {path.relative_to(VAULT_ROOT)}"
