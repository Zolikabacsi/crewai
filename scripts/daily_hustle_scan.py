#!/usr/bin/env python3
"""Daily side hustle scan — run via cron.

Uses Reddit free JSON API (no Playwright), RSS feeds, and direct HTTP.
No browser automation needed.
"""

import os
import sys
import json
import uuid
import feedparser
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

# Add project root + sibling packages to path.
# insert(0,...) prepends — last insert ends up FIRST in sys.path (correct search priority).
WORKTREE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(WORKTREE_ROOT / "ai_council"))  # 3rd in list → resolved 3rd
sys.path.insert(0, str(WORKTREE_ROOT / "src"))          # 2nd in list → resolved 2nd
sys.path.insert(0, str(WORKTREE_ROOT))                   # 1st in list → resolved 1st

from src.tools import OpportunityStorageTool
from slack.slack_client import SlackClient, build_extraordinary_alert, build_hustle_report
# ai_council imported lazily in consult_council to avoid loading crewai_tools at module level

# ── Reddit ──────────────────────────────────────────────────────────────────
REDDIT_SUBREDDITS = [
    "sidehustle",
    "Entrepreneur",
    "passive_income",
    "startups",
    "smallbusiness",
    "freelance",
    "WorkOnline",
    "digital_marketing",
    "ecommerce",
    "juststart",
    "SideProject",
    "FIRE",
    "financialindependence",
]

REDDIT_KEYWORDS = [
    "side hustle", "extra income", "make money", "earn money",
    "passive income", "online business", "startup", "build",
    "launch", "first customer", "freelance", "SaaS", "digital product",
]

_REDDIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HustleScanner/1.0)",
    "Accept": "application/json",
}


def scrape_reddit_posts(seen_tracker) -> list[dict]:
    """Fetch hot posts from multiple subreddits via Reddit JSON API."""
    posts = []
    for sub in REDDIT_SUBREDDITS:
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit=25"
            resp = requests.get(url, headers=_REDDIT_HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            children = data.get("data", {}).get("children", [])
            for child in children:
                post = child["data"]
                title = post.get("title", "")
                body = post.get("selftext", "")
                score = post.get("score", 0)
                num_comments = post.get("num_comments", 0)
                created = post.get("created_utc", 0)
                url = post.get("url", "")
                permalink = f"https://reddit.com{post.get('permalink', '')}"

                if not seen_tracker.is_new(permalink):
                    continue

                # Keyword relevance check
                combined = f"{title} {body}".lower()
                if not any(kw in combined for kw in REDDIT_KEYWORDS):
                    continue

                posts.append({
                    "title": title,
                    "body": body,
                    "score": score,
                    "comments": num_comments,
                    "subreddit": sub,
                    "url": permalink,
                    "created_utc": created,
                    "source": "reddit",
                })
        except Exception as e:
            print(f"Warning: {type(e).__name__}: {e}")
            continue
    return posts


# ── RSS feeds ────────────────────────────────────────────────────────────────
RSS_FEEDS = [
    {
        "name": "HackerNews",
        "url": "https://hnrss.org/newest?q=startup+OR+saas+OR+business+OR+side+hustle+OR+passive+income",
        "keywords": ["hustle", "revenue", "launch", "income", "startup", "business"],
    },
    {
        "name": "IndieHackers",
        "url": "https://www.indiehackers.com/feed.xml",
        "keywords": ["hustle", "revenue", "launch", "income", "build", "started"],
    },
    {
        "name": "ProductHunt",
        "url": "https://www.producthunt.com/feed",
        "keywords": ["launch", "product", "free", "tool", "app"],
    },
]


def scrape_rss_feeds(seen_tracker) -> list[dict]:
    """Parse RSS feeds for relevant hustle content."""
    posts = []
    for feed_cfg in RSS_FEEDS:
        try:
            resp = requests.get(
                feed_cfg["url"],
                headers={"User-Agent": "Mozilla/5.0 HustleScanner/1.0"},
                timeout=15,
            )
            if resp.status_code != 200:
                continue
            feed = feedparser.parse(resp.text)
            for entry in feed.entries[:20]:
                title = getattr(entry, "title", "")
                summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
                link = getattr(entry, "link", "")
                published = getattr(entry, "published", "")

                # Clean HTML from summary
                import re
                summary = re.sub(r"<[^>]+>", " ", summary)
                summary = re.sub(r"\s+", " ", summary).strip()

                if not seen_tracker.is_new(link):
                    continue

                combined = f"{title} {summary}".lower()
                if not any(kw in combined for kw in feed_cfg["keywords"]):
                    continue

                posts.append({
                    "title": title,
                    "body": summary[:500],
                    "score": 0,
                    "comments": 0,
                    "subreddit": feed_cfg["name"],
                    "url": link,
                    "created_utc": 0,
                    "source": "rss",
                })
        except Exception as e:
            print(f"Warning: {type(e).__name__}: {e}")
            continue
    return posts


# ── Scraper ─────────────────────────────────────────────────────────────────
def scrape_sources(seen_tracker) -> list[dict]:
    """Gather opportunities from all sources."""
    all_posts = []

    reddit_posts = scrape_reddit_posts(seen_tracker)
    all_posts.extend(reddit_posts)

    rss_posts = scrape_rss_feeds(seen_tracker)
    all_posts.extend(rss_posts)

    return all_posts


# ── Scoring ─────────────────────────────────────────────────────────────────
SCORE_KEYWORDS_TITLE = [
    "passive income", "automated", "scale", "profitable", "first paying",
    "reached $", "make $", "earned $", "$1k", "$10k", "mrp", "monthly",
]

SCORE_KEYWORDS_BODY = [
    "passive", "automated", "scalable", "profitable", "customer",
    "revenue", "income", "earn", "marketplace", "SaaS", "digital product",
]

TRASH_KEYWORDS = ["ONLYOFFICE", "WTF", "nsfw", "[removed]", "[deleted]"]


def score_opportunity(post: dict) -> Optional[float]:
    """Score a post. Returns None if filtered out as noise."""
    title = post.get("title", "")
    body = post.get("body", "")
    score = post.get("score", 0)
    source = post.get("source", "reddit")

    if source == "reddit":
        combined_score = score
    else:
        # RSS posts have no vote score — use recency as proxy
        combined_score = 10

    title_lower = title.lower()
    body_lower = body.lower()

    # Filter noise
    if any(kw in title_lower for kw in TRASH_KEYWORDS):
        return None

    # Engagement filter (reddit)
    if source == "reddit" and score < 5:
        return None

    # Keyword scoring
    pts = 0
    for kw in SCORE_KEYWORDS_TITLE:
        if kw in title_lower:
            pts += 3
    for kw in SCORE_KEYWORDS_BODY:
        if kw in body_lower:
            pts += 1

    # Comments bonus
    comments = post.get("comments", 0)
    if comments > 50:
        pts += 4
    elif comments > 20:
        pts += 2
    elif comments > 5:
        pts += 1

    # Reddit score bonus
    if score > 500:
        pts += 5
    elif score > 100:
        pts += 3
    elif score > 20:
        pts += 1

    return pts + combined_score * 0.01


# ── AI Council ────────────────────────────────────────────────────────────────
def consult_council_single(opp: dict) -> tuple[str, dict]:
    """
    Consult the AI board partners (CMO, CFO, Coach, Devil's Advocate)
    on a single opportunity. Returns (title, council_text) tuple.

    Graceful fallback: if council fails, returns an error string.
    """
    import subprocess, json, os
    from pathlib import Path

    topic = (
        f"Evaluate this side hustle:\n\n"
        f"Title: {opp.get('title', '')}\n"
        f"Source: {opp.get('source', 'reddit')} ({opp.get('subreddit', '')})\n"
        f"Body: {opp.get('body', '')[:600]}\n"
        f"Hustle Score: {opp.get('hustle_score', '?')}\n"
    )

    partners_prompt = (
        'You are consulting 4 AI board partners on the following side hustle opportunity.\n'
        'For each partner, give a focused 2-3 sentence assessment based on their role.\n'
        'Reply with ONLY a JSON object (no markdown, no code fences):\n\n'
        '{"CMO": "[market viability, audience fit, GTM path, growth channels]",\n'
        ' "CFO": "[financial viability, startup costs, income potential, time ROI]",\n'
        ' "Coach": "[founder fit, time commitment, skill match, mindset risks]",\n'
        ' "DevilsAdvocate": "[what could go wrong, biggest risks, failure modes]"\n'
        '}\n\n'
        'OPPORTUNITY TO EVALUATE:\n'
        + topic
    )

    claude_bin = Path.home() / ".local" / "bin" / "claude"

    try:
        result = subprocess.run(
            [str(claude_bin), "-p", "--model", "MiniMax-M2.7", "--output-format", "json",
             partners_prompt],
            stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=90,
            env={**os.environ, "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_AUTH_TOKEN", "")},
        )

        if result.returncode == 0 and result.stdout.strip():
            try:
                raw = json.loads(result.stdout.strip())
                text = raw.get("result", raw.get("content", raw.get("text", "")))
                if isinstance(text, str):
                    data = json.loads(text)
                else:
                    data = text
                lines = [f"*{role}:* {assessment}" for role, assessment in data.items()]
                return (opp.get("title", ""), "\n".join(lines))
            except json.JSONDecodeError:
                fallback = raw.get("result", "") if isinstance(raw, dict) else str(raw)
                return (opp.get("title", ""), str(fallback)[:500])
        else:
            return (opp.get("title", ""), f"[council error: {result.stderr[:200] if result.stderr else 'no output'}]")
    except subprocess.TimeoutExpired:
        return (opp.get("title", ""), "[council timeout]")
    except Exception as e:
        return (opp.get("title", ""), f"[council unavailable: {e}]")


def consult_council(opp: dict) -> str:
    """Backward-compatible wrapper — calls single and returns just the opinion."""
    _, opinion = consult_council_single(opp)
    return opinion


# ── Storage ─────────────────────────────────────────────────────────────────
def save_opportunity(opp: dict):
    try:
        store = OpportunityStorageTool()
        store._run(action="save", data=json.dumps(opp))
    except Exception as e:
        print(f"Storage error: {e}")


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now():%H:%M:%S}] Starting hustle scan...")

    seen_tracker = SeenTracker()

    # Scrape
    print("Scraping sources...")
    posts = scrape_sources(seen_tracker)
    print(f"  → {len(posts)} raw posts collected")

    # Score
    scored = []
    skip_count = 0
    for post in posts:
        s = score_opportunity(post)
        if s is None:
            skip_count += 1
            seen_tracker.mark_seen(post["url"])
            continue
        post["hustle_score"] = round(s, 1)
        scored.append(post)
        seen_tracker.mark_seen(post["url"])

    scored.sort(key=lambda x: x["hustle_score"], reverse=True)
    print(f"Found {len(scored)} ranked opportunities ({skip_count} filtered)")

    # Prune old entries and flush pending writes to disk once
    seen_tracker.prune()
    seen_tracker.flush()

    # Top 10 only for Slack
    # Build scores dict and summary for Slack
    for opp in scored:
        # Note: income and time_hrs_week are not available from scraper data
        # The hustle_score is a composite of engagement metrics, not earnings/time
        opp["scores"] = {
            "income": "?",
            "time_hrs_week": "?",
        }
        # Extract first meaningful line as summary
        body = opp.get("body", "")
        if body:
            lines = [l.strip() for l in body.split("\n") if l.strip() and len(l.strip()) > 20]
            opp["summary"] = lines[0][:200] if lines else body[:150]
        else:
            opp["summary"] = opp.get("title", "")

    top = scored[:10]

    # Consult board partners on ALL top opportunities — in parallel
    print(f"Consulting AI board partners on top {len(top)} opportunities (parallel)...")
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_opp = {executor.submit(consult_council_single, opp): opp for opp in top}
        for future in as_completed(future_to_opp):
            opp = future_to_opp[future]
            try:
                title, opinion = future.result()
                opp["council_feedback"] = {"coach": opinion}
                print(f"  [done] {title[:60]}")
            except Exception as e:
                print(f"  [error] {opp.get('title', '')[:60]}: {e}")

    # Save all
    for opp in scored:
        save_opportunity(opp)

    # Slack
    print("Sending Slack notifications...")
    hustle_webhook = os.getenv("HUSTLE_WEBHOOK_URL", os.getenv("SLACK_WEBHOOK_URL", ""))
    if scored:
        report = build_hustle_report(top, len(scored), skip_count)
        SlackClient.send(report, webhook_url=hustle_webhook)
        print(f"Slack: sent {len(top)} opportunities")
    else:
        SlackClient.send(
            f"📊 Side Hustle Report — {datetime.now():%Y-%m-%d}\n\nNo new opportunities today.",
            webhook_url=hustle_webhook,
        )

    print("Scan complete.")


# ── Seen tracker (inline, no external dependency) ──────────────────────────
STATE_FILE = Path(__file__).parent.parent / "output" / "hustle_seen.json"
RETENTION_DAYS = 14


class SeenTracker:
    def __init__(self):
        self._data = {"seen": []}
        if STATE_FILE.exists():
            try:
                self._data = json.loads(STATE_FILE.read_text())
            except Exception:
                pass
        self._pending_writes: list[dict] = []

    def _save(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(self._data, indent=2))

    def flush(self):
        """Write all pending entries to disk."""
        if self._pending_writes:
            self._data["seen"].extend(self._pending_writes)
            self._pending_writes = []
            self._save()

    def is_new(self, url: str) -> bool:
        if not url:
            return True
        cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
        for entry in self._data["seen"]:
            if entry["url"] == url and entry["seen_date"] >= cutoff:
                return False
        return True

    def mark_seen(self, url: str):
        if not url:
            return
        self._pending_writes.append({
            "url": url,
            "seen_date": datetime.now().strftime("%Y-%m-%d"),
        })

    def prune(self):
        cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
        self._data["seen"] = [
            e for e in self._data["seen"] if e["seen_date"] >= cutoff
        ]


if __name__ == "__main__":
    main()
