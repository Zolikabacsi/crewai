"""Agent Storage Module — shared storage utilities for all C-suite agents.

This module provides:
- VaultStorageTool: crewAI tool for saving documents to the vault folder structure
- AgentMemory: wrapper around Sisyphus MemoryService for cross-session memory
- StorageService: singleton that coordinates both storage backends

Usage:
    from src.agent_storage import VaultStorageTool, AgentMemory, get_storage

    # As a tool (create one instance per agent)
    vault_tool = VaultStorageTool(agent_folder="Aestas_CFO", sub_folder="analyses")
    result = vault_tool._run(content="# My Analysis", title="Q4 Financial Review")

    # As a memory wrapper
    memory = AgentMemory(agent_name="CFO")
    memory.save("Key insight from analysis...", memory_type="decision", importance=8)
    prior_context = memory.search("quarterly planning")
"""

from src.agent_storage.vault_tool import VaultStorageTool
from src.agent_storage.memory_integration import AgentMemory
from src.agent_storage.storage_service import StorageService

# Singleton instance
_storage_service = None


def get_storage() -> StorageService:
    """Get or create the StorageService singleton."""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service


__all__ = [
    "VaultStorageTool",
    "AgentMemory",
    "StorageService",
    "get_storage",
]

# ── Agent Message Bus ─────────────────────────────────────────────────────────
# Redis pub/sub for agent-to-agent communication
from src.agent_bus.message_bus import AgentBus

__all__ += ["AgentBus"]
