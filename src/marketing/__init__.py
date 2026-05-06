"""Marketing skills integration module.

This module provides:
- SkillLoaderTool: Load marketing methodology on demand
- skills_index: Mapping of agents to their relevant skills
- crew: Marketing crew with CMO leading sub-agents
"""

from .skill_loader import SkillLoaderTool
from .skills_index import AGENT_SKILLS
from .crew import run_marketing_campaign

__all__ = ["SkillLoaderTool", "AGENT_SKILLS", "run_marketing_campaign"]
