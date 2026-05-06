"""AgentMemory — wrapper around Sisyphus MemoryService for agent cross-session memory.

Agents use this to:
- SAVE: Store key facts, decisions, context after each task
- SEARCH: Retrieve relevant memories before starting new tasks
- RECALL: Get previous council sessions, analyses, decisions

The memory service runs at http://localhost:18789
"""

import requests
from datetime import datetime
from typing import Optional

MEMORY_SERVICE_URL = "http://localhost:18789"


class AgentMemory:
    """
    Wrapper around Sisyphus MemoryService for agent cross-session memory.

    Agents use this to:
    - SAVE: Store key facts, decisions, context after each task
    - SEARCH: Retrieve relevant memories before starting new tasks
    - RECALL: Get previous council sessions, analyses, decisions

    Note: This is described in agent backstories rather than imported directly
    to avoid circular imports with the memory service.
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.base_url = MEMORY_SERVICE_URL

    def save(
        self,
        content: str,
        memory_type: str = "agent_memory",
        importance: int = 7,
        tags: Optional[list] = None
    ) -> str:
        """Save a memory to Sisyphus.

        Types:
        - agent_memory: General knowledge/insights from this agent
        - council_session: Board meeting outputs
        - decision: Key strategic decisions
        - context: Project/company state
        - backup: Vault document backup
        """
        payload = {
            "content": content,
            "type": memory_type,
            "importance": importance,
            "metadata": {
                "agent": self.agent_name,
                "tags": tags or [],
                "timestamp": datetime.now().isoformat()
            }
        }
        try:
            resp = requests.post(f"{self.base_url}/memory", json=payload, timeout=10)
            if resp.status_code == 200:
                return f"[memory saved: {memory_type}]"
            return f"[memory save failed: {resp.status_code}]"
        except Exception as e:
            return f"[memory unavailable: {e}]"

    def search(self, query: str, limit: int = 5) -> str:
        """Search memories relevant to current task."""
        try:
            resp = requests.get(
                f"{self.base_url}/memories",
                params={"query": query, "limit": limit},
                timeout=10
            )
            if resp.status_code == 200:
                memories = resp.json()
                if not memories:
                    return ""
                lines = ["[Prior Context]"]
                for m in memories:
                    lines.append(f"- {m.get('content', '')[:200]}")
                return "\n".join(lines)
            return ""
        except:
            return ""

    def save_council_output(
        self,
        topic: str,
        agent_outputs: dict,
        recommendation: str = ""
    ) -> str:
        """Save a board council session result."""
        content = f"""# {self.agent_name} — Council Session: {topic}

## Topic
{topic}

## Agent Outputs
{chr(10).join(f"### {k}: {v}" for k, v in agent_outputs.items())}

## Recommendation
{recommendation}

## Timestamp
{datetime.now().isoformat()}
"""
        return self.save(content, memory_type="council_session", importance=9, tags=["council", "strategic"])
