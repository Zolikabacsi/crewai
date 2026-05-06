"""CMO Agent — Chief Marketing Officer for Aestas Healthcare.

This agent serves in two modes:
1. BOARD MODE: Votes on business ideas presented by the CEO (Zoltan) as a board member
   with equal voting rights to CFO, CCO, COO. Assesses market fit, go-to-market viability.
2. OPERATIONAL MODE: Leads marketing strategy for Aestas Healthcare project including
   content strategy, SEO/GEO, social media coordination via Zernio, copywriting, and analytics.

The agent has deep medical/healthcare knowledge and understands Hungarian market context.
"""

from crewai import Agent
from crewai.llm import LLM
from crewai.tools import BaseTool
from crewai_tools import DirectoryReadTool, FileReadTool, TavilySearchTool
from ..config import Config
from pathlib import Path

import os

# Ensure environment is configured for custom endpoints
if Config.ANTHROPIC_AUTH_TOKEN:
    os.environ["ANTHROPIC_API_KEY"] = Config.ANTHROPIC_AUTH_TOKEN
if Config.ANTHROPIC_BASE_URL:
    os.environ["ANTHROPIC_BASE_URL"] = Config.ANTHROPIC_BASE_URL.rstrip("/v1")

# Vault path for Aestas Marketing content
VAULT_MARKETING_PATH = Path("/home/zoltan/srv/vault/Second Brain/raw/Aestas_CMO")

# Zernio API configuration (used for social media posting)
ZERNIO_API_KEY_PATH = Path.home() / ".claude" / ".env.zernio"
ZERNIO_BASE_URL = "https://zernio.com/api/v1"


def get_llm():
    """Create LLM instance for CMO agent with MiniMax-M2.7 model."""
    return LLM(
        provider="anthropic",
        model="MiniMax-M2.7",
        api_key=Config.ANTHROPIC_AUTH_TOKEN,
        base_url=Config.ANTHROPIC_BASE_URL.rstrip("/v1") if Config.ANTHROPIC_BASE_URL else "https://chat.ultimateai.org",
    )


def _load_zernio_api_key() -> str | None:
    """Load Zernio API key from ~/.claude/.env.zernio"""
    try:
        if ZERNIO_API_KEY_PATH.exists():
            for line in ZERNIO_API_KEY_PATH.read_text().splitlines():
                if line.startswith("ZERNIO_API_KEY="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None


class ZernioPostTool(BaseTool):
    """Custom tool for posting content via Zernio API.

    This tool allows the CMO to publish posts to LinkedIn and other social platforms
    using the Zernio API. It supports posting immediately or scheduling for later.
    """

    name: str = "ZernioPostTool"
    description: str = (
        "Post content to social media platforms (LinkedIn, Facebook, Twitter/X, etc.) via Zernio API. "
        "Expects a JSON payload with 'content' (post text), 'platforms' (array of platform+accountId objects), "
        "'publishNow' (bool), and optionally 'scheduledTime' (ISO timestamp). "
        "Example platforms entry: {'platform': 'linkedin', 'accountId': '692c289df43160a0bc99992d'}. "
        "Use list_posts() first to see available accounts and their IDs."
    )

    def _run(
        self,
        content: str = "",
        platforms: list = None,
        publish_now: bool = True,
        scheduled_time: str = None,
        visibility: str = "public",
    ) -> str:
        """
        Post content via Zernio API.

        Args:
            content: The post text content
            platforms: List of dicts with 'platform' and 'accountId' keys
            publish_now: If True, publish immediately; if False, schedule
            scheduled_time: ISO timestamp for scheduled posts (required if publish_now=False)
            visibility: 'public', 'private', or 'connections'

        Returns:
            JSON response from Zernio API
        """
        import json
        import urllib.request

        api_key = _load_zernio_api_key()
        if not api_key:
            return '{"error": "Zernio API key not found at ~/.claude/.env.zernio"}'

        if not platforms:
            return '{"error": "No platforms specified. Provide at least one platform with accountId."}'

        if not content:
            return '{"error": "No content provided."}'

        payload = {
            "content": content,
            "platforms": platforms,
            "publishNow": publish_now,
            "visibility": visibility,
        }

        if not publish_now and scheduled_time:
            payload["scheduledTime"] = scheduled_time

        # Write payload to temp file to avoid JSON escaping issues
        temp_payload_path = "/tmp/zernio_post_payload.json"
        with open(temp_payload_path, "w") as f:
            json.dump(payload, f)

        try:
            req = urllib.request.Request(
                f"{ZERNIO_BASE_URL}/posts",
                data=open(temp_payload_path, "rb"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return f'{{"error": "HTTP {e.code}: {e.read().decode("utf-8")}"}}'
        except Exception as e:
            return f'{{"error": "{str(e)}"}}'


class ZernioListAccountsTool(BaseTool):
    """Custom tool to list all connected social media accounts via Zernio API."""

    name: str = "ZernioListAccountsTool"
    description: str = (
        "List all social media accounts connected to Zernio. "
        "Returns account IDs, platforms, and display names. "
        "Use this to find the correct accountId for posting to a specific platform."
    )

    def _run(self) -> str:
        """Get all connected accounts from Zernio."""
        import urllib.request

        api_key = _load_zernio_api_key()
        if not api_key:
            return '{"error": "Zernio API key not found"}'

        try:
            req = urllib.request.Request(
                f"{ZERNIO_BASE_URL}/accounts",
                headers={"Authorization": f"Bearer {api_key}"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return f'{{"error": "HTTP {e.code}"}}'
        except Exception as e:
            return f'{{"error": "{str(e)}"}}'


class ZernioListPostsTool(BaseTool):
    """Custom tool to list recent posts from Zernio."""

    name: str = "ZernioListPostsTool"
    description: str = (
        "List recent posts from Zernio. Optionally filter by platform. "
        "Returns post content, status, publish dates, and platform URLs. "
        "Use platforms parameter as URL-encoded JSON array, e.g.: "
        "[{'platform': 'linkedin', 'accountId': '692c289df43160a0bc99992d'}]"
    )

    def _run(self, platforms: str = None, limit: int = 20) -> str:
        """List recent posts, optionally filtered by platform."""
        import json
        import urllib.parse
        import urllib.request

        api_key = _load_zernio_api_key()
        if not api_key:
            return '{"error": "Zernio API key not found"}'

        url = f"{ZERNIO_BASE_URL}/posts?limit={limit}"
        if platforms:
            encoded = urllib.parse.quote(platforms)
            url = f"{ZERNIO_BASE_URL}/posts?platforms={encoded}&limit={limit}"

        try:
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return f'{{"error": "HTTP {e.code}"}}'
        except Exception as e:
            return f'{{"error": "{str(e)}"}}'


class CMO(Agent):
    """Chief Marketing Officer agent with dual board/operational modes.

    The CMO has deep expertise in:
    - Healthcare marketing and medical content strategy
    - Hungarian and European healthcare markets
    - B2B/B2C digital marketing channels
    - Social media strategy and multi-platform campaigns
    - SEO/GEO for healthcare content
    - Brand positioning and messaging

    In BOARD MODE, the CMO evaluates business ideas with rigor, considering:
    - Market size and growth potential
    - Competitive landscape and positioning
    - Go-to-market feasibility
    - Marketing spend efficiency
    - Regulatory considerations for healthcare products

    In OPERATIONAL MODE, the CMO leads:
    - Content strategy for Aestas Healthcare (medical articles, patient education in Hungarian)
    - SEO/GEO optimization briefs
    - Social media coordination via Zernio (LinkedIn, Facebook, Twitter, etc.)
    - Copywriting briefs and review
    - Analytics monitoring and optimization
    """

    def __init__(self):
        super().__init__(
            role="Chief Marketing Officer (CMO)",
            goal=(
                "Drive market success for Aestas Healthcare through strategic marketing leadership. "
                "In board meetings: provide decisive votes on business viability based on market analysis. "
                "In operations: lead content, social, SEO, and copywriting to build brand authority and "
                "patient engagement in the Hungarian and European healthcare markets."
            ),
            backstory=(
                "You are a battle-tested CMO with 20+ years of experience in healthcare marketing, "
                "having built brands for pharma giants and health-tech startups alike. You hold a board "
                "seat at Aestas Healthcare with full voting rights alongside the CFO, CCO, and COO. "
                "Your medical background includes deep expertise in dermatology, aesthetics, and "
                "preventive healthcare — you can debate clinical trial design with investigators and "
                "craft patient journey maps that convert. You speak Hungarian natively and navigate "
                "European healthcare regulations with ease. You've scaled D2C healthcare brands from "
                "0 to €10M ARR through disciplined digital marketing and thought leadership. "
                "You believe in evidence-based marketing: every claim traceable, every campaign measurable."
            ),
            verbose=Config.VERBOSE,
            tools=[
                DirectoryReadTool(),
                FileReadTool(),
                TavilySearchTool(),  # Web search — requires TAVILY_API_KEY env var
                ZernioPostTool(),
                ZernioListAccountsTool(),
                ZernioListPostsTool(),
            ],
            llm=get_llm(),
        )


def get_cmo(tools: list = None) -> CMO:
    """Factory function to create the CMO agent.
    
    Args:
        tools: Override tools list. Pass empty list [] when using CMO as a
               hierarchical manager agent (CrewAI forbids manager agents having tools).
    """
    if tools is not None:
        # Create CMO with custom tools (for manager use, pass tools=[])
        class CMOManager(CMO):
            def __init__(self):
                super().__init__()
                # Override tools with provided list
                object.__setattr__(self, 'tools', tools)
        
        return CMOManager()
    return CMO()
