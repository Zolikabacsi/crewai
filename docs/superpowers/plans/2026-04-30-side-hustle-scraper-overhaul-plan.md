# Side Hustle Scraper Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the useless placeholder-driven scraper with a pipeline that fetches real opportunities, deduplicates by URL, scores them, and produces rich Slack cards.

**Architecture:** Playwright-based scraper with three phases: (1) fetch HN "Who is hiring" threads + Reddit posts with content, (2) dedup + score, (3) format + send. No LLM calls in the critical path — Coach uses graceful degradation.

**Tech Stack:** Python 3, Playwright, BeautifulSoup, Slack webhook, existing crewAI tools pattern.

---

## File Map

| File | Role |
|---|---|
| `src/tools/web_scraper_tool.py` | Fetch HN threads, parse job comments; fetch Reddit posts, extract body |
| `scripts/daily_hustle_scan.py` | Dedup, scoring, coach, orchestration |
| `slack/slack_client.py` | Build rich card strings |
| `tests/test_hustle_dedup.py` | Dedup logic tests |
| `tests/test_hustle_scoring.py` | Income/time scoring tests |
| `tests/test_hustle_format.py` | Rich card format tests |

---

### Task 1: HN "Who is hiring" Thread Parser

**Files:**
- Modify: `src/tools/web_scraper_tool.py` — add `_scrape_hn_hiring()` method
- Test: `tests/test_hn_parser.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hn_parser.py
import sys
sys.path.insert(0, ".")
from src.tools.web_scraper_tool import WebScraperTool

def test_hn_hiring_returns_job_structured_data():
    """When scraping HN 'who is hiring', returns dicts with title, salary, time fields."""
    tool = WebScraperTool()
    # Mock is tricky here — test the parsing logic on a known HTML snippet
    from src.tools.web_scraper_tool import HNHiringParser
    html = """
    <tr class='athing'>
      <td class='title'>
        <a href="item?id=123">Ask HN: Who is hiring? (March 2026)</a>
      </td>
    </tr>
    """
    # HNHiringParser.extract_thread_links(html) → [dict with url, title]
    assert HNHiringParser.extract_thread_links(html)[0]["url"] == "item?id=123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.config/superpowers/worktrees/crewai/crypto-research && python -m pytest tests/test_hn_parser.py -v`
Expected: FAIL — `HNHiringParser` not defined

- [ ] **Step 3: Add HNHiringParser class and extract_thread_links()**

Add to bottom of `src/tools/web_scraper_tool.py`:

```python
class HNHiringParser:
    """Parse HN 'Who is hiring' monthly threads for job opportunities."""

    @staticmethod
    def extract_thread_links(html: str, max_months: int = 3) -> list[dict]:
        """Extract hiring thread links from submitted page. Returns list of {url, title, month}."""
        soup = BeautifulSoup(html, "html.parser")
        links = soup.select(".titleline > a")
        threads = []
        for a in links:
            text = a.get_text(strip=True)
            if "who is hiring" in text.lower():
                threads.append({
                    "url": a.get("href", ""),
                    "title": text,
                    "month": HNHiringParser._extract_month(text),
                })
                if len(threads) >= max_months:
                    break
        return threads

    @staticmethod
    def _extract_month(title: str) -> str:
        m = re.search(r'\(([A-Za-z]+ \d{4})\)', title)
        return m.group(1) if m else "unknown"

    @staticmethod
    def parse_job_comments(html: str) -> list[dict]:
        """Parse a hiring thread page for job comment entries."""
        soup = BeautifulSoup(html, "html.parser")
        comments = soup.select(".comment")
        jobs = []
        for com in comments[:30]:  # first 30 comments
            text = com.get_text(strip=True)
            if len(text) < 50:
                continue
            title = HNHiringParser._extract_job_title(text)
            if title:
                income = HNHiringParser._extract_salary(text)
                jobs.append({
                    "title": title,
                    "income": income,
                    "time": HNHiringParser._estimate_time(text),
                    "startup_cost": "low" if "remote" in text.lower() else "medium",
                    "description": text[:300],
                    "url": "",
                })
        return jobs

    @staticmethod
    def _extract_job_title(text: str) -> str:
        """First line or first 80 chars is usually the job title."""
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if len(line) > 10:
                return line[:80]

    @staticmethod
    def _extract_salary(text: str) -> str:
        """Look for salary mentions like €50k, $120k, 80-150k."""
        m = re.search(r'[€$£](\d+)[\dk]?', text, re.IGNORECASE)
        if m:
            return m.group(1)
        return "?"

    @staticmethod
    def _estimate_time(text: str) -> str:
        if "part-time" in text.lower() or "part time" in text.lower():
            return "20"
        if "contract" in text.lower() or "freelance" in text.lower():
            return "10"
        return "40"
```

- [ ] **Step 4: Add `_scrape_hn_hiring()` to WebScraperTool**

```python
def _scrape_hn_hiring(self, context) -> str:
    """Scrape HN 'Who is hiring' monthly threads — rich source of real opportunities."""
    try:
        page = context.new_page()
        resp = page.goto(
            "https://news.ycombinator.com/submitted?id=whoishiring",
            timeout=20000,
            wait_until="domcontentloaded",
        )
        page.wait_for_timeout(2000)
        content = page.content()
        page.close()

        soup = BeautifulSoup(content, "html.parser")
        links = soup.select(".titleline > a")
        threads = [a for a in links if "who is hiring" in a.get_text(strip=True).lower()][:3]
        
        all_jobs = []
        for thread_link in threads:
            thread_title = thread_link.get_text(strip=True)
            thread_url = thread_link.get("href", "")
            # Navigate to the thread
            page2 = context.new_page()
            target = thread_url if thread_url.startswith("http") else f"https://news.ycombinator.com/{thread_url}"
            resp2 = page2.goto(target, timeout=25000, wait_until="domcontentloaded")
            page2.wait_for_timeout(3000)
            thread_html = page2.content()
            page2.close()
            
            jobs = HNHiringParser.parse_job_comments(thread_html)
            for job in jobs:
                job["source"] = f"HN {thread_title}"
                job["url"] = target
            all_jobs.extend(jobs)
        
        lines = []
        for job in all_jobs[:10]:  # max 10
            income_str = f"€{job['income']}/mo" if job["income"] != "?" else "€?/mo"
            lines.append(
                f"[HN Hiring] {job['title']}\n"
                f"  Income: {income_str} | Time: {job['time']} hrs/wk\n"
                f"  {job['description'][:200]}\n"
                f"  URL: {job['url']}"
            )
        return "\n\n".join(lines) if lines else "[HN Hiring] No threads found"
    except Exception as e:
        return f"[HN Hiring] Error: {e}"
```

- [ ] **Step 5: Update WebScraperTool._run() to include HN hiring scraper**

In the `_run` method, add:
```python
if source in ("hackernews", "all"):
    results.append(self._scrape_hackernews(context))
    results.append(self._scrape_hn_hiring(context))  # ADD THIS
```

- [ ] **Step 6: Run tests**

Run: `cd ~/.config/superpowers/worktrees/crewai/crypto-research && python -m pytest tests/test_hn_parser.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd ~/.config/superpowers/worktrees/crewai/crypto-research
git add src/tools/web_scraper_tool.py tests/test_hn_parser.py
git commit -m "feat(hustle): add HN 'Who is hiring' thread parser with structured job extraction"
```

---

### Task 2: Reddit Post-Content Parser (Not Just Titles)

**Files:**
- Modify: `src/tools/web_scraper_tool.py` — replace `_scrape_reddit()` logic
- Test: `tests/test_reddit_parser.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reddit_parser.py
import sys
sys.path.insert(0, ".")

def test_skip_ask_hn_posts():
    """Posts with 'Ask HN' in title should be filtered out."""
    from src.tools.web_scraper_tool import RedditPostParser
    posts = [
        {"title": "Ask HN: Who wants to be hired?", "url": "http://example.com/1"},
        {"title": "My side hustle making €5k/mo", "url": "http://example.com/2"},
    ]
    filtered = RedditPostParser.filter_opportunities(posts)
    assert len(filtered) == 1
    assert "side hustle" in filtered[0]["title"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reddit_parser.py -v`
Expected: FAIL — `RedditPostParser` not defined

- [ ] **Step 3: Add RedditPostParser class**

Add to `src/tools/web_scraper_tool.py`:

```python
class RedditPostParser:
    """Parse Reddit posts into structured opportunity records."""

    @staticmethod
    def filter_opportunities(posts: list[dict]) -> list[dict]:
        """Remove non-opportunity posts (job listings, meta posts)."""
        skip_patterns = ["ask hn", "who is hiring", "who wants to be hired",
                         "monthly thread", "meta discussion"]
        result = []
        for post in posts:
            title_lower = post.get("title", "").lower()
            if any(p in title_lower for p in skip_patterns):
                continue
            result.append(post)
        return result

    @staticmethod
    def score_monetization(post_body: str) -> dict:
        """Score post for monetization signals and estimate income/time."""
        body_lower = post_body.lower()
        scores = {
            "income": "?",
            "time_hrs_week": "?",
            "startup_cost": "low",
        }
        
        # Income signals
        if "€" in post_body or "$" in post_body:
            m = re.search(r'[€$]([\d,]+)', post_body)
            if m:
                raw = m.group(1).replace(",", "")
                try:
                    monthly = int(raw)
                    if monthly < 10000:
                        scores["income"] = str(monthly)
                    else:
                        scores["income"] = str(monthly // 12)
                except ValueError:
                    pass
        
        # Time signals
        if "passive" in body_lower or "automated" in body_lower:
            scores["time_hrs_week"] = "5"
        elif "side hustle" in body_lower or "freelance" in body_lower:
            scores["time_hrs_week"] = "15"
        else:
            scores["time_hrs_week"] = "?"
        
        # Startup cost
        if any(x in body_lower for x in ["no money", "free", "zero cost", "under €100"]):
            scores["startup_cost"] = "low"
        elif any(x in body_lower for x in ["investment", "cost", "expense", "paid"]):
            scores["startup_cost"] = "medium"
        
        return scores

    @staticmethod
    def extract_summary(post_body: str) -> str:
        """Extract the first meaningful sentence as summary."""
        lines = [l.strip() for l in post_body.split("\n") if l.strip()]
        for line in lines:
            if len(line) > 20:
                return line[:200]
        return post_body[:200]
```

- [ ] **Step 4: Update `_scrape_reddit()` to fetch post content**

Replace the existing `_scrape_reddit()` with:

```python
def _scrape_reddit(self, context) -> str:
    """Scrape Reddit — navigate into posts, extract content for monetization analysis."""
    lines = []
    for sub in ["sidehustle", "Entrepreneur", "passive_income"]:
        try:
            page = context.new_page()
            url = f"https://old.reddit.com/r/{sub}/search.json?q=side+hustle+OR+passive+income+OR+make+money&sort=top&t=month&restrict_sr=1"
            resp = page.goto(url, timeout=20000)
            page.wait_for_timeout(2000)
            content = page.content()
            page.close()

            if resp.status != 200:
                lines.append(f"[Reddit/r/{sub}] HTTP {resp.status}")
                continue

            soup = BeautifulSoup(content, "html.parser")
            # Get post links from search results
            post_links = soup.select(".result a[data-type='Submission']")[:5]
            if not post_links:
                post_links = soup.select(".titleline > a")[:5]

            posts = []
            for a in post_links:
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if href.startswith("/"):
                    href = f"https://old.reddit.com{href}"
                posts.append({"title": title, "url": href})

            # Filter out non-opportunities
            filtered = RedditPostParser.filter_opportunities(posts)

            # Navigate into each post to get body
            for post in filtered[:3]:
                page2 = context.new_page()
                try:
                    resp2 = page2.goto(post["url"] + ".json", timeout=20000)
                    page2.wait_for_timeout(1500)
                    import json as json_module
                    data = json_module.loads(page2.content()) if resp2.status == 200 else {}
                    post_body = ""
                    if isinstance(data, list) and len(data) > 1:
                        post_body = data[0].get("data", {}).get("children", [{}])[0].get("data", {}).get("selftext", "")
                    page2.close()

                    scores = RedditPostParser.score_monetization(post_body)
                    summary = RedditPostParser.extract_summary(post_body)
                    income_str = f"€{scores['income']}/mo" if scores['income'] != "?" else "€?/mo"
                    lines.append(
                        f"[Reddit/r/{sub}] {post['title']}\n"
                        f"  Income: {income_str} | Time: {scores['time_hrs_week']} hrs/wk\n"
                        f"  {summary}\n"
                        f"  URL: {post['url']}"
                    )
                except Exception:
                    page2.close()
                    continue
        except Exception as e:
            lines.append(f"[Reddit/r/{sub}] Error: {e}")
    return "\n".join(lines) if lines else "[Reddit] Could not reach Reddit"
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_reddit_parser.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/tools/web_scraper_tool.py tests/test_reddit_parser.py
git commit -m "feat(hustle): rewrite Reddit scraper — fetch post content, not just titles"
```

---

### Task 3: URL Dedup Layer

**Files:**
- Modify: `scripts/daily_hustle_scan.py` — add dedup logic
- Test: `tests/test_hustle_dedup.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hustle_dedup.py
import sys, json, tempfile, os
sys.path.insert(0, ".")
from scripts.daily_hustle_scan import DedupTracker

def test_url_seen_within_90_days_is_skipped():
    td = tempfile.mkdtemp()
    tracker = DedupTracker(td)
    tracker.mark_seen("https://example.com/post1")
    assert tracker.is_new("https://example.com/post1") == False

def test_url_older_than_90_days_is_not_skipped():
    td = tempfile.mkdtemp()
    tracker = DedupTracker(td)
    # Manually add old entry
    old_entry = {"url": "https://example.com/old", "seen_date": "2025-01-01"}
    tracker._data["seen"] = [old_entry]
    tracker._save()
    assert tracker.is_new("https://example.com/old") == True

def test_new_url_is_processed():
    td = tempfile.mkdtemp()
    tracker = DedupTracker(td)
    assert tracker.is_new("https://example.com/fresh") == True
    tracker.mark_seen("https://example.com/fresh")
    assert tracker.is_new("https://example.com/fresh") == False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_hustle_dedup.py -v`
Expected: FAIL — `DedupTracker` not defined

- [ ] **Step 3: Add DedupTracker to daily_hustle_scan.py**

Add at top of `scripts/daily_hustle_scan.py`:

```python
import os
import sys
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

WORKTREE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(WORKTREE_ROOT))

DEDUP_FILE = Path.home() / ".claude" / "hustle_seen_urls.json"
RETENTION_DAYS = 90


class DedupTracker:
    """Track seen URLs, skip duplicates within 90-day window."""

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or DEDUP_FILE
        self._data = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                pass
        return {"seen": []}

    def _save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self._data, indent=2))

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
        self._data["seen"].append({
            "url": url,
            "seen_date": datetime.now().strftime("%Y-%m-%d"),
        })
        self._save()

    def prune(self):
        """Remove entries older than RETENTION_DAYS."""
        cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
        self._data["seen"] = [
            e for e in self._data["seen"] if e["seen_date"] >= cutoff
        ]
        self._save()
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_hustle_dedup.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/daily_hustle_scan.py tests/test_hustle_dedup.py
git commit -m "feat(hustle): add DedupTracker — 90-day URL dedup window"
```

---

### Task 4: Coach Graceful Degradation + Rich Card Format

**Files:**
- Modify: `scripts/daily_hustle_scan.py` — fix `consult_council()`, update pipeline
- Modify: `slack/slack_client.py` — add `build_rich_card()` and `build_hustle_report()`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hustle_format.py
import sys
sys.path.insert(0, ".")

def test_rich_card_format():
    from slack.slack_client import build_rich_card
    card = build_rich_card(
        title="Freelance AI Consultant",
        income="800-1500",
        time="15",
        summary="Setup AI workflows for small businesses",
        source="HN Who is hiring (Mar 2026)",
        url="https://news.ycombinator.com/item?id=123",
        coach="High-margin, growing demand. Watch for saturation.",
    )
    assert "Freelance AI Consultant" in card
    assert "800-1500" in card
    assert "15 hrs/wk" in card
    assert "HN Who is hiring" in card
    assert "High-margin" in card

def test_coach_unavailable_fallback():
    from slack.slack_client import build_rich_card
    card = build_rich_card(
        title="SaaS Tool",
        income="2000",
        time="5",
        summary="Passive income from a niche tool",
        source="Reddit/r/sidehustle",
        url="https://reddit.com/r/sidehustle/posts/123",
        coach=None,
    )
    assert "Coach assessment unavailable" in card
    assert "placeholder" not in card.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_hustle_format.py -v`
Expected: FAIL — `build_rich_card` not defined

- [ ] **Step 3: Add build_rich_card() to slack_client.py**

Read existing `slack/slack_client.py` first, then add:

```python
def build_rich_card(
    title: str,
    income: str,
    time: str,
    summary: str,
    source: str,
    url: str,
    coach: str | None,
) -> str:
    income_str = f"€{income}/mo" if income != "?" else "€?/mo"
    coach_str = coach if coach else "Coach assessment unavailable — check source link"
    return (
        f"🎯 {title} — {income_str} | {time} hrs/wk\n"
        f"   {summary}\n"
        f"   Source: {source} | URL: {url}\n"
        f"   💡 {coach_str}"
    )


def build_hustle_report(opportunities: list[dict], new_count: int, skip_count: int) -> str:
    """Build the daily hustle report with rich cards."""
    header = f"📊 Side Hustle Daily Report — {datetime.now().strftime('%Y-%m-%d')}\n"
    header += f"Found {new_count} new opportunities ({skip_count} skipped as duplicates)\n\n"

    cards = []
    for opp in opportunities[:10]:  # max 10
        card = build_rich_card(
            title=opp.get("title", "?"),
            income=opp.get("scores", {}).get("income", "?"),
            time=opp.get("scores", {}).get("time_hrs_week", "?"),
            summary=opp.get("summary", opp.get("description", ""))[:150],
            source=opp.get("source", "?"),
            url=opp.get("url", ""),
            coach=opp.get("council_feedback", {}).get("coach"),
        )
        cards.append(card)

    return header + "\n\n".join(f"{i+1}. {c}" for i, c in enumerate(cards))
```

- [ ] **Step 4: Fix consult_council() with graceful degradation**

Replace the placeholder in `scripts/daily_hustle_scan.py`:

```python
def consult_council(opportunity: dict) -> dict:
    """Consult Coach with graceful degradation on failure."""
    try:
        coach = CoachPartner()
        prompt = f"""Evaluate this side hustle opportunity:

Title: {opportunity.get('title', '?')}
Description: {opportunity.get('description', '?')[:200]}
Income: €{opportunity.get('scores', {}).get('income', '?')}/month
Time: {opportunity.get('scores', {}).get('time_hrs_week', '?')} hrs/week
Startup cost: €{opportunity.get('scores', {}).get('startup_cost', '?')}

Provide a one-line assessment of viability and one risk to watch."""
        coach_response = coach.evaluate(prompt)  # real LLM call
    except Exception:
        coach_response = None  # graceful fallback — build_rich_card handles None
    return {"coach": coach_response, "devils_advocate": ""}
```

- [ ] **Step 5: Update main() in daily_hustle_scan.py to use dedup + rich cards**

Replace the `main()` function:

```python
def main():
    print(f"=== Side Hustle Daily Scan — {datetime.now().isoformat()} ===")

    # 1. Fetch web
    print("Scanning web sources...")
    web_results = run_web_scan()

    # 2. Parse into opportunities
    opportunities = evaluate_opportunity(web_results)
    print(f"Found {len(opportunities)} raw opportunities")

    # 3. Deduplicate
    dedup = DedupTracker()
    new_opportunities = []
    skip_count = 0
    for opp in opportunities:
        url = opp.get("url", "")
        if not url or dedup.is_new(url):
            if url:
                dedup.mark_seen(url)
            new_opportunities.append(opp)
        else:
            skip_count += 1

    # 4. Score
    scored = []
    for opp in new_opportunities:
        opp["summary"] = RedditPostParser.extract_summary(
            opp.get("description", "")
        ) if "Reddit" in opp.get("source", "") else opp.get("description", "")[:150]
        scored.append(opp)

    print(f"Found {len(scored)} new opportunities ({skip_count} skipped as duplicates)")

    # 5. Consult council (graceful)
    for opp in scored:
        council = consult_council(opp)
        opp["council_feedback"] = council

    # 6. Save
    for opp in scored:
        save_opportunity(opp)

    # 7. Send Slack
    print("Sending Slack notifications...")
    if scored:
        report = build_hustle_report(scored, len(scored), skip_count)
        SlackClient.send(report)
    else:
        SlackClient.send(f"📊 Side Hustle Daily Report — {datetime.now().strftime('%Y-%m-%d')}\n\nNo new opportunities today.")

    print("Scan complete.")
```

- [ ] **Step 6: Update evaluate_opportunity() to extract URL**

In `evaluate_opportunity()`, capture the URL field:

```python
# After extracting source and title, also grab URL
url = ""
for line in lines:
    if line.strip().startswith("URL:"):
        url = line.replace("URL:", "").strip()
        break

opp = {
    ...
    "url": url,
}
```

- [ ] **Step 7: Run format tests**

Run: `python -m pytest tests/test_hustle_format.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add scripts/daily_hustle_scan.py slack/slack_client.py tests/test_hustle_format.py
git commit -m "feat(hustle): coach graceful degradation + rich card Slack format"
```

---

### Task 5: End-to-End Smoke Test

**Files:**
- Run: `python scripts/daily_hustle_scan.py` locally in the worktree

- [ ] **Step 1: Run the pipeline**

Run: `cd ~/.config/superpowers/worktrees/crewai/crypto-research && python scripts/daily_hustle_scan.py 2>&1`
Expected: Completes without crash, outputs to Slack, shows dedup count

- [ ] **Step 2: Verify no placeholder text**

Check: `grep -i "placeholder\|Coach consultation" ~/.claude/side_hustle_opportunities.json 2>/dev/null || echo "No placeholders found"`

- [ ] **Step 3: Commit with test result note**

```bash
git add -m "test: verify pipeline runs and produces non-placeholder output"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| HN "Who is hiring" parser | Task 1 |
| Reddit post-content (not titles) | Task 2 |
| Dedup by URL, 90-day window | Task 3 |
| Coach graceful degradation | Task 4 |
| Rich card format | Task 4 |
| ≤10 opportunities per report | Task 4 (enforced in `build_hustle_report` with `[:10]`) |
| Report header with skip count | Task 4 |
| Zero placeholder text | Task 4 (coach returns `None` → fallback message) |

**Plan complete.** Saved to `docs/superpowers/plans/2026-04-30-side-hustle-scraper-overhaul-plan.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?