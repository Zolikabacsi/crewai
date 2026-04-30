"""Memory service integration for AI Council."""

import requests
from typing import Optional


class MemoryService:
    """Sisyphus Memory Service integration."""

    def __init__(self, base_url: str = "http://localhost:18789"):
        self.base_url = base_url
        self.session_id = None

    def health_check(self) -> bool:
        """Check if memory service is available."""
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except:
            return False

    def save_memory(
        self,
        content: str,
        memory_type: str = "general",
        importance: int = 5,
        metadata: Optional[dict] = None
    ) -> dict:
        """Save a memory to the service."""
        payload = {
            "content": content,
            "type": memory_type,
            "importance": importance,
            "metadata": metadata or {}
        }
        resp = requests.post(f"{self.base_url}/memory", json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def search_memories(self, query: str = "", limit: int = 10) -> list:
        """Search memories."""
        resp = requests.get(
            f"{self.base_url}/memories",
            params={"query": query, "limit": limit},
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def get_recent(self, limit: int = 20) -> list:
        """Get recent memories."""
        resp = requests.get(
            f"{self.base_url}/memories/recent",
            params={"limit": limit},
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def get_stats(self) -> dict:
        """Get memory statistics."""
        resp = requests.get(f"{self.base_url}/stats", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def save_council_result(
        self,
        topic: str,
        result: str,
        agents: list,
        recommendation: str = ""
    ) -> dict:
        """Save a council session result."""
        content = f"""# AI Council Session: {topic}

## Topic
{topic}

## Participating Agents
{', '.join(agents)}

## Recommendation
{recommendation}

## Full Results
{result}
"""
        return self.save_memory(
            content=content,
            memory_type="council_session",
            importance=8,
            metadata={
                "topic": topic,
                "agents": agents,
                "type": "strategic_advisory"
            }
        )

    def get_previous_councils(self, limit: int = 5) -> list:
        """Get previous council sessions."""
        resp = requests.get(
            f"{self.base_url}/memories",
            params={"type": "council_session", "limit": limit},
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()


# Global instance
_memory_service = None


def get_memory_service() -> MemoryService:
    """Get or create memory service instance."""
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service