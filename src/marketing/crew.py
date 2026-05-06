"""Marketing Crew — CMO-led marketing workflow for Aestas Healthcare.

This module provides a CrewAI crew that chains:
1. CMO (Chief Marketing Officer) — Strategic lead, delegates to sub-agents
2. SEOGEOSpecialist — Keyword research, content briefs, optimization
3. SocialMediaManager — Content calendar, platform management
4. Copywriter — Patient education copy, marketing materials

The CMO synthesizes inputs from sub-agents and produces final output.
"""

from crewai import Crew, Agent, Task
from crewai.process import Process
from crewai.llm import LLM

import subprocess
import json
import os
from pathlib import Path

# Import agents - using ai_council for full MarketingCrew
# Note: ai_council.src.crew is imported lazily inside functions to avoid circular import
from ..agents.cmo import get_cmo
from ..agents.seogeo import get_seogeo
from ..agents.social_manager import get_social_manager
from ..agents.copywriter import get_copywriter

# Import skill loader
from .skill_loader import SkillLoaderTool

# Import config
from ..config import Config


def _setup_llm_env():
    """Ensure environment is configured for custom LLM endpoints."""
    if Config.ANTHROPIC_AUTH_TOKEN:
        os.environ["ANTHROPIC_API_KEY"] = Config.ANTHROPIC_AUTH_TOKEN
    if Config.ANTHROPIC_BASE_URL:
        os.environ["ANTHROPIC_BASE_URL"] = Config.ANTHROPIC_BASE_URL.rstrip("/v1")


def run_marketing_campaign(task: str, output_file: str = None) -> str:
    """Run a complete marketing campaign through the CMO-led crew.

    Args:
        task: The marketing task to execute (e.g., "Write a LinkedIn post about X")
        output_file: Optional path to save the final output

    Returns:
        The final synthesized output from the CMO as a dict with keys: cmO, seogeo, social, copywriter
    """
    # Pre-fetch relevant vault context for marketing/brand
    vault_ctx = ""
    try:
        from src.tools.second_brain_tool import SecondBrainKnowledgeTool
        t = SecondBrainKnowledgeTool()
        ctx = t._run(query=task, sections=["CMO", "Brand"])
        if ctx and "not found" not in ctx.lower()[:100] and "No results" not in ctx:
            vault_ctx = f"\n\n## Relevant Context from Second Brain Vault\n{ctx}\n"
    except Exception:
        pass

    # Build comprehensive multi-role marketing prompt
    prompt = f"""You are the CMO (Chief Marketing Officer) leading a marketing team for Aestas Healthcare.

Your team consists of three specialized sub-agents:
- SEOGEOSpecialist: Keyword research, SEO/GEO optimization, content structure
- SocialMediaManager: Social platform strategy, content calendar, engagement
- Copywriter: Patient education copy, marketing materials, headlines, CTAs

Task: {task}
{vault_ctx}---

## SEOGEOSpecialist Section

You are the SEO/GEO Specialist for Aestas Healthcare. Use the marketingskills repo at ~/srv/marketingskills if needed for methodology.

Research and provide:
1. Relevant keywords for Hungarian healthcare audience
2. SEO optimization tips and GEO (Generative Engine Optimization) guidance
3. Content structure recommendations
4. Meta description suggestions

Format your output as detailed, actionable recommendations.

---

## SocialMediaManager Section

You are the Social Media Manager for Aestas Healthcare. Use the marketingskills repo at ~/srv/marketingskills if needed for methodology.

Research and provide:
1. Best social platforms for Hungarian healthcare audience (LinkedIn, Facebook, Instagram, etc.)
2. Content format recommendations (posts, carousels, stories, videos)
3. Engagement strategy and timing
4. Hashtag recommendations

Format your output as detailed, actionable recommendations.

---

## Copywriter Section

You are the Copywriter for Aestas Healthcare. Use the marketingskills repo at ~/srv/marketingskills if needed for methodology.

Produce:
1. Primary marketing copy for the task (LinkedIn post, email, ad copy, etc.)
2. Alternative headline/hook options (at least 2-3 variations)
3. Call-to-action suggestions
4. Patient education angle if applicable

Format your output as polished, ready-to-use copy.

---

## CMO Synthesis Section

As CMO, synthesize all inputs from your sub-agents above and produce the FINAL marketing deliverable:

1. Combine SEO/GEO insights with compelling copy
2. Ensure messaging is appropriate for Hungarian healthcare audience
3. Final content should be polished and ready for publication
4. Include any relevant hashtags and calls-to-action

---

Output your response ONLY as a JSON object with this exact structure:
{{"cmO": "...", "seogeo": "...", "social": "...", "copywriter": "..."}}

Each field should contain the text content for that section. Do not include any other text outside the JSON.
"""

    # Execute via Claude Code subprocess with MiniMax-M2.7
    claude_bin = Path.home() / ".local" / "bin" / "claude"
    
    try:
        result = subprocess.run(
            [str(claude_bin), "-p", "--model", "MiniMax-M2.7", "--output-format", "json"],
            input=prompt,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300,
        )
        
        if result.returncode != 0:
            error_msg = f"Claude Code error (exit {result.returncode}): {result.stderr}"
            if output_file:
                Path(output_file).parent.mkdir(parents=True, exist_ok=True)
                Path(output_file).write_text(error_msg, encoding="utf-8")
            return error_msg
        
        # Parse JSON envelope response
        envelope = json.loads(result.stdout.strip())
        text = envelope.get("result", "")

        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            # Remove ```json ... ``` wrapper
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[0].startswith("```") else text
            text = text.strip()

        # Try JSON parse first
        try:
            inner = json.loads(text) if isinstance(text, str) else text
        except json.JSONDecodeError:
            # Try to find and extract JSON object by brace matching
            start = text.find("{")
            if start == -1:
                inner = {"raw": text}
            else:
                depth = 0
                end = start
                for i, c in enumerate(text[start:], start):
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                json_str = text[start:end]
                try:
                    inner = json.loads(json_str)
                except Exception:
                    inner = {"raw": text[start:end]}

        # Optionally save output
        if output_file:
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            Path(output_file).write_text(json.dumps(inner, indent=2, ensure_ascii=False), encoding="utf-8")

        return inner
        
    except subprocess.TimeoutExpired:
        error_msg = "Claude Code subprocess timed out after 180 seconds"
        if output_file:
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            Path(output_file).write_text(error_msg, encoding="utf-8")
        return error_msg
    except json.JSONDecodeError as e:
        error_msg = f"Failed to parse Claude Code response as JSON: {e}\nRaw output: {result.stdout[:500] if result.stdout else 'empty'}"
        if output_file:
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            Path(output_file).write_text(error_msg, encoding="utf-8")
        return error_msg
    except Exception as e:
        error_msg = f"Unexpected error running Claude Code: {e}"
        if output_file:
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            Path(output_file).write_text(error_msg, encoding="utf-8")
        return error_msg


def run_simple_linkedin_post(topic: str) -> str:
    """Run a simple LinkedIn post task.

    Note: This function delegates to ai_council.src.crew.run_marketing_task
    (which uses the more sophisticated ai_council crew) rather than using
    this module's own crew. This is intentional for consistency with the
    ai_council workflow.
    """
    # Lazy import to avoid circular import with ai_council.src.agents
    from ai_council.src.crew import run_marketing_task as _run_marketing_task
    return _run_marketing_task(f"Write a professional LinkedIn post about: {topic}")
