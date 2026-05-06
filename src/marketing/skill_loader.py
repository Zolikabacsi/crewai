"""SkillLoaderTool — On-demand marketing skill methodology loader.

This tool reads specific SKILL.md files from the marketingskills repo
only when the agent needs them. This keeps context lean while providing
access to detailed methodologies.
"""

import os
from crewai.tools import BaseTool
from pydantic import Field
from pathlib import Path


class SkillLoaderTool(BaseTool):
    """Loads a marketing skill methodology from the marketingskills repo.
    
    Use when working on SEO, copywriting, social media, content strategy,
    competitor analysis, or any other marketing discipline covered by the
    marketingskills repository.
    
    Args:
        skill_name: The name of the skill directory (e.g., "ai-seo", "copywriting")
    
    Returns:
        The full content of the SKILL.md file for the requested skill.
    """
    
    name: str = "load_skill"
    description: str = (
        "Loads a marketing skill methodology from the marketingskills repo. "
        "Use when working on SEO, copywriting, social media, content strategy, "
        "competitor analysis, or any marketing discipline. "
        "Input should be the skill name (e.g., 'ai-seo', 'copywriting', 'content-strategy')."
    )
    
    marketingskills_path: str = Field(
        default_factory=lambda: os.environ.get(
            "MARKETINGSKILLS_PATH",
            str(Path.home() / "srv/crewai/marketingskills/skills")
        ),
        description="Base path to the marketingskills repository"
    )
    
    def _run(self, skill_name: str) -> str:
        """Read the SKILL.md file for the requested skill."""
        skill_path = Path(self.marketingskills_path) / skill_name / "SKILL.md"
        
        if not skill_path.exists():
            available = ", ".join(self._list_available_skills())
            return f"Skill '{skill_name}' not found. Available skills: {available}"
        
        try:
            content = skill_path.read_text(encoding="utf-8")
            return f"=== {skill_name.upper()} SKILL ===\n\n{content}"
        except Exception as e:
            return f"Error reading skill '{skill_name}': {str(e)}"
    
    def _list_available_skills(self) -> list:
        """List all available skill directories."""
        base = Path(self.marketingskills_path)
        if not base.exists():
            return []
        return sorted([d.name for d in base.iterdir() if d.is_dir()])
