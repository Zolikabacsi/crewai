"""Reddit scraper — tries official Reddit API first, falls back to Pushshift.

Reddit API: requires a script app registered at reddit.com/prefs/apps + approval.
  Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in .env.

Pushshift: public mirror, no auth, works immediately.
  Coverage is ~1 day behind live Reddit — fine for daily scans.
"""

import os
import urllib.request
import urllib.parse
import json

import praw
import prawcore
from crewai.tools import BaseTool

SUBREDDITS = ["startups", "Entrepreneur", "sidehustle", "passive_income"]
QUERY = "side hustle OR passive income OR monetize OR extra income"


class RedditScraperTool(BaseTool):
    name: str = "RedditScraperTool"
    description: str = (
        "Search Reddit for side hustle and income opportunities. "
        "Pass search='all' to search r/startups, r/Entrepreneur, r/sidehustle, r/passive_income. "
        "Returns a list of posts with title, score, and URL."
    )

    def _run(self, search: str = "all") -> str:
        targets = SUBREDDITS if search == "all" else [search]

        # 1. Try official Reddit API via PRAW
        client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
        client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()

        if client_id and client_secret:
            result = self._via_praw(targets)
            if result:
                return result
            # PRAW failed (e.g. app not approved) — fall through to Pushshift

        # 2. Fall back to Pushshift (no auth, works immediately)
        return self._via_pushshift(targets)

    # ── Official Reddit API (PRAW) ─────────────────────────────────────────

    def _via_praw(self, targets: list[str]) -> str | None:
        """Fetch via PRAW OAuth2. Returns None on auth failure so caller falls back."""
        client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
        client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()

        try:
            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent="SideHustleScout/1.0 (contact: zoltan@example.com)",
            )
            # Verify auth — fetching a public object fails fast if not approved
            _ = reddit.subreddit("all").id
        except prawcore.exceptions.ResponseException:
            # Auth failed (401/403) — app not approved or bad credentials — fall back to Pushshift
            return None
        except Exception:
            # Any other error (network, etc.) — also fall back to Pushshift
            return None

        lines = []
        for sub in targets:
            try:
                subreddit = reddit.subreddit(sub)
                posts = subreddit.search(
                    QUERY,
                    sort="top",
                    time_filter="month",
                    limit=5,
                )
                for post in posts:
                    lines.append(
                        f"[Reddit/r/{sub}] {post.title}\n"
                        f"  Score: {post.score} | Comments: {post.num_comments}\n"
                        f"  URL: https://reddit.com{post.permalink}"
                    )
            except Exception as e:
                lines.append(f"[Reddit/r/{sub}] Error: {e}")

        return "\n".join(lines) if lines else None

    # ── Pushshift fallback ──────────────────────────────────────────────────

    def _via_pushshift(self, targets: list[str]) -> str:
        """Public Reddit data mirror — no auth, ~1 day behind live."""
        lines = []
        for sub in targets:
            try:
                posts = self._fetch_pushshift(sub, limit=5)
                if not posts:
                    lines.append(f"[Reddit/r/{sub}] No posts found")
                    continue
                for post in posts:
                    title = post.get("title", "?")
                    score = post.get("score", 0)
                    num_comments = post.get("num_comments", 0)
                    permalink = post.get("permalink", "")
                    if permalink and not permalink.startswith("http"):
                        permalink = f"https://reddit.com{permalink}"
                    lines.append(
                        f"[Reddit/r/{sub}] {title}\n"
                        f"  Score: {score} | Comments: {num_comments}\n"
                         f"  URL: {permalink}"
                    )
            except Exception as e:
                lines.append(f"[Reddit/r/{sub}] Error: {e}")

        return "\n".join(lines) if lines else "[Reddit] No posts found"

    def _fetch_pushshift(self, subreddit: str, limit: int = 5) -> list[dict]:
        params = urllib.parse.urlencode({
            "q": QUERY,
            "subreddit": subreddit,
            "sort": "score",
            "size": limit,
            "sort_type": "score",
        })
        url = f"https://api.pullpush.io/reddit/submission/search/?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "SideHustleScout/1.0"})
        with urllib.request.urlopen(req, timeout=20000) as resp:
            data = json.loads(resp.read())
        posts = data.get("data", [])

        if not posts:
            params2 = urllib.parse.urlencode({
                "subreddit": subreddit,
                "sort": "score",
                "size": limit,
            })
            url2 = f"https://api.pullpush.io/reddit/submission/search/?{params2}"
            req2 = urllib.request.Request(url2, headers={"User-Agent": "SideHustleScout/1.0"})
            with urllib.request.urlopen(req2, timeout=20000) as resp2:
                data2 = json.loads(resp2.read())
            posts = data2.get("data", [])

        return posts
