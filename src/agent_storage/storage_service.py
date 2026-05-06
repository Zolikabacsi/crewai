"""StorageService — singleton that coordinates Vault file storage and Sisyphus memory.

This service provides a unified interface for agents to:
- Save outputs to both vault (file) and memory (searchable)
- Search prior context from memory before tasks
- Backup vault documents to memory

Usage:
    storage = get_storage()
    storage.save_output(
        agent_name="CFO",
        content="# Q4 Analysis\n\nKey findings...",
        title="Q4 Financial Review",
        doc_type="analyses",
        memory_type="decision"
    )
    prior = storage.search_prior_context("quarterly planning")
"""

from src.agent_storage.vault_tool import VaultStorageTool
from src.agent_storage.memory_integration import AgentMemory
from typing import Optional


class StorageService:
    """Coordinates Vault file storage and Sisyphus memory integration."""

    # Agent to vault folder mapping
    AGENT_FOLDERS = {
        "Aestas_CFO": ("Aestas_CFO", "analyses"),
        "Aestas_CTO": ("Aestas_CTO", "tech_decisions"),
        "Aestas_COO": ("Aestas_COO", "operational_docs"),
        "Aestas_CMO": ("Aestas_CMO", "campaigns"),
    }

    def __init__(self):
        self._vault_cache = {}  # agent_folder -> VaultStorageTool instance

    def _get_vault_tool(self, agent_folder: str, sub_folder: str) -> VaultStorageTool:
        """Get or create a VaultStorageTool for the given agent."""
        key = f"{agent_folder}:{sub_folder}"
        if key not in self._vault_cache:
            self._vault_cache[key] = VaultStorageTool(
                agent_folder=agent_folder,
                sub_folder=sub_folder
            )
        return self._vault_cache[key]

    def save_output(
        self,
        agent_name: str,
        content: str,
        title: str,
        doc_type: Optional[str] = None,
        memory_type: str = "agent_memory",
        importance: int = 7,
        tags: Optional[list] = None,
        backup_to_memory: bool = True,
    ) -> dict:
        """Save an output to both vault and optionally memory.

        Args:
            agent_name: The agent name (e.g., "CFO", "CTO") or full folder (e.g., "Aestas_CFO")
            content: The document content (markdown)
            title: Short descriptive title
            doc_type: Sub-folder type (defaults based on agent_name mapping)
            memory_type: Type of memory (for memory service)
            importance: Memory importance (1-10)
            tags: Tags for both vault and memory
            backup_to_memory: Whether to also save to Sisyphus memory

        Returns:
            dict with 'vault' and 'memory' status strings
        """
        # Normalize agent name to folder
        if not agent_name.startswith("Aestas_"):
            folder_name = f"Aestas_{agent_name.upper()}"
        else:
            folder_name = agent_name

        # Determine doc_type from agent mapping if not provided
        if doc_type is None:
            _, default_sub = self.AGENT_FOLDERS.get(
                folder_name, (folder_name, "general")
            )
            doc_type = default_sub

        # Save to vault
        vault_tool = self._get_vault_tool(folder_name, doc_type)
        metadata = {
            "agent": folder_name,
            "doc_type": doc_type,
            "tags": tags or [],
        }
        vault_result = vault_tool._run(content, title, metadata)

        # Optionally backup to memory
        memory_result = ""
        if backup_to_memory:
            memory = AgentMemory(agent_name=folder_name)
            memory_result = memory.save(
                content=f"# {title}\n\n{content}",
                memory_type=memory_type,
                importance=importance,
                tags=tags,
            )

        return {
            "vault": vault_result,
            "memory": memory_result,
        }

    def search_prior_context(self, query: str, agent_name: str = None, limit: int = 5) -> str:
        """Search memory for relevant prior context.

        Args:
            query: Search query string
            agent_name: Optional agent name to scope the search
            limit: Maximum number of results

        Returns:
            Formatted string of prior context memories
        """
        memory = AgentMemory(agent_name=agent_name or "System")
        return memory.search(query, limit=limit)
