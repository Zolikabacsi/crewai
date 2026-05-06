"""Zernio API tools for social media posting.

These tools allow the CMO to publish posts to LinkedIn and other social platforms
using the Zernio API.
"""

from crewai.tools import BaseTool
from pathlib import Path

# Zernio API configuration
ZERNIO_API_KEY_PATH = Path.home() / ".claude" / ".env.zernio"
ZERNIO_BASE_URL = "https://zernio.com/api/v1"


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
