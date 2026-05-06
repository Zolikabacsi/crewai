"""Marketing Crew — CMO-led hierarchical crew for Aestas Healthcare."""

import os
import sys
from pathlib import Path

# Allow imports from src/ (sibling package at project root)
# crew.py is at ai_council/src/ → 3 levels up = project root ~/srv/crewai/
_CREWAI_ROOT = str(Path(__file__).parent.parent.parent)
if _CREWAI_ROOT not in sys.path:
    sys.path.insert(0, _CREWAI_ROOT)

from crewai import Crew, Task
from crewai.process import Process
from .agents import CMOPartner
from src.agents.seogeo import SEOGEOSpecialist
from src.agents.social_manager import SocialMediaManager
from src.agents.copywriter import Copywriter
from ai_council.src.config import Config

def _setup_llm_env():
    if Config.ANTHROPIC_AUTH_TOKEN:
        os.environ["ANTHROPIC_API_KEY"] = Config.ANTHROPIC_AUTH_TOKEN
    if Config.ANTHROPIC_BASE_URL:
        os.environ["ANTHROPIC_BASE_URL"] = Config.ANTHROPIC_BASE_URL.rstrip("/v1")

class MarketingCrew:
    """CMO-led hierarchical crew for Aestas Healthcare marketing.
    
    CMO (manager) → delegates to → SEOGEOSpecialist, SocialMediaManager, Copywriter
    Sub-agents → execute with marketingskills → return outputs
    CMO → synthesizes → final deliverable
    """
    
    def __init__(self):
        _setup_llm_env()
        self.cmo = CMOPartner()
        self.seogeo = SEOGEOSpecialist()
        self.social = SocialMediaManager()
        self.copywriter = Copywriter()
    
    def kickoff(self, task: str) -> str:
        cmo_task = Task(
            description=f"""CMO LEADING: {task}

SKILL ROUTING — ALWAYS follow this flow:
1. LOAD relevant marketingskills first via SkillLoaderTool:
   - SEO/keywords → ai-seo + content-strategy
   - Social posts → social-content + copywriting
   - Landing/copy pages → copywriting + page-cro
   - Email sequences → cold-email + email-sequence
   - Competitor analysis → competitor-profiling
   - CRO/forms/popups → form-cro + popup-cro + signup-flow-cro
   - Analytics/tracking → analytics-tracking
   - A/B testing → ab-test-setup

2. DELEGATE to the right sub-agent:
   - SEOGEOSpecialist → keyword research, content briefs, SEO optimization
   - SocialMediaManager → content calendars, post writing, platform strategy, Zernio posting
   - Copywriter → all written content, drafts, editing, copy variations

3. COLLECT outputs from sub-agents

4. SYNTHESIZE into the final deliverable

For simple tasks (single post, quick copy): produce directly using loaded skills.
For complex tasks (multi-channel campaigns): delegate to sub-agents, then synthesize.""",
            agent=self.cmo,
            expected_output="Final marketing deliverable",
        )
        
        crew = Crew(
            agents=[self.cmo, self.seogeo, self.social, self.copywriter],
            tasks=[cmo_task],
            process=Process.hierarchical,
            manager_agent=self.cmo,
            verbose=Config.VERBOSE,
        )
        return crew.kickoff()

def run_marketing_task(task: str) -> str:
    """One-shot marketing task through CMO-led crew."""
    return MarketingCrew().kickoff(task)
