# Side Hustle Scraper Overhaul — Design Spec

## Context

The current `daily_hustle_scan.py` produces a useless report: 27 "opportunities" that are mostly Reddit search titles ("Ask HN: Who is hiring?") and duplicate posts. The Coach is a hardcoded placeholder. The scraper grabs headlines, not opportunities.

## What Changes

### 1. HN Scraper — Parse "Who is hiring" Threads

**Source:** `news.ycombinator.com/submitted?id=whoishiring`

**Flow:**
1. Fetch monthly thread links (current month + previous 2 months)
2. For each thread, navigate to comments and parse job-comment structure
3. Extract: title, salary range, location, remote/onsite, tech stack

**Scoring:**
- Income: from salary mention (e.g. "€120k" → €10k/mo), else estimate from job type
- Time: full-time → 40 hrs, part-time → 20 hrs, contract → 10 hrs
- Startup cost: remote → low (€0–100), onsite → medium (€500+)

**Edge cases:**
- Thread with no "Ask HN" in title → skip (not a hiring thread)
- Comment without salary → assign "?/mo" but mark as "estimate from type"
- Thread older than 2 months → skip

### 2. Reddit Scraper — Post Content, Not Titles

**Source:** `old.reddit.com/r/sidehustle/search.json?sort=top&t=month`

**Flow:**
1. Fetch top 10 posts
2. Skip posts with "Ask HN" in title (job listings, not opportunities)
3. Navigate into each post, extract title + first paragraph
4. Score for monetization signals: digital product, SaaS, freelance service, affiliate, etc.

**Dedup:** Already-handled by dedup layer (see section 4).

### 3. Dedup Layer

**State file:** `~/.claude/hustle_seen_urls.json`

```json
{
  "seen": [
    {"url": "https://news.ycombinator.com/item?id=123", "seen_date": "2026-04-30"},
    ...
  ],
  "retention_days": 90
}
```

**On new opportunity:**
- Check if URL is in `seen` with `seen_date` within 90 days
- If yes → skip and increment skip counter
- If no → add to `seen` and process

**Report header shows:** `Found X new opportunities (Y skipped as duplicates)`

### 4. Coach — Graceful Degradation

```python
def consult_council(opportunity: dict) -> dict:
    coach = CoachPartner()
    try:
        coach_response = coach.evaluate(opportunity)  # real LLM call
    except Exception as e:
        coach_response = "Coach assessment unavailable — check source link"
    return {"coach": coach_response, "devils_advocate": ""}
```

- If LLM call fails → return descriptive message, don't hide it
- `devils_advocate` stays empty (not wired in current version)

### 5. Output Format — Rich Cards

**Format string:**
```
🎯 {title} — €{income}/mo | {time} hrs/wk
   {one-line summary from post body}
   Source: {source_name} | URL: {url}
   💡 {coach_response}
```

**Example:**
```
🎯 Freelance AI Automation Consultant — €800–1,500/mo | 15 hrs/wk
   Turnkey setup of AI workflows for small businesses. No recurring cost.
   Source: HN Who is hiring (Mar 2026) | URL: https://news.ycombinator.com/item?id=...
   💡 High-margin, growing demand. Watch for competition saturation.
```

**If coach unavailable:**
```
🎯 {title} — €{income}/mo | {time} hrs/wk
   {summary}
   Source: {source_name} | URL: {url}
   💡 Coach assessment unavailable — check source link
```

## Pipeline Order

```
fetch_sources()
  → deduplicate_by_url()
  → score_opportunities()
  → consult_council()  # graceful
  → format_rich_cards()
  → send_to_slack()
```

## Components

| Component | File | Responsibility |
|---|---|---|
| HN parser | `web_scraper_tool.py` | Fetch threads, parse job comments |
| Reddit parser | `web_scraper_tool.py` | Fetch posts, extract monetization signals |
| Dedup | `daily_hustle_scan.py` | URL dedup against seen list |
| Scorer | `daily_hustle_scan.py` | Income/time/startup scoring |
| Coach | `daily_hustle_scan.py` | LLM call with graceful fallback |
| Formatter | `slack_client.py` | Build rich card string |
| Entry point | `scripts/daily_hustle_scan.py` | Orchestrate pipeline |

## Data Model

```python
{
  "id": "uuid",
  "title": str,
  "description": str,          # first paragraph, max 300 chars
  "summary": str,              # one-line extraction
  "scores": {
    "income": "800-1500",      # euro/mo, "?" if unknown
    "time_hrs_week": "15",     # hrs, "?" if unknown
    "startup_cost": "low",     # low / medium / high
  },
  "council_feedback": {"coach": str},
  "status": "pending",
  "discovered_date": "YYYY-MM-DD",
  "source": str,              # e.g. "HN Who is hiring (Mar 2026)"
  "url": str,
}
```

## Success Criteria

1. Report shows ≤10 opportunities (quality over quantity)
2. Zero "Coach consultation (placeholder)" text
3. Zero duplicate URLs in same report
4. Each card has: title, income, time, source URL, coach or unavailable message
5. Report header: "Found X new opportunities (Y skipped as duplicates)"