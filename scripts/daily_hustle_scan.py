#!/usr/bin/env python3
"""Daily side hustle scan — run via cron.

Scrapes web sources, checks vault reports, consults council agents,
routes findings to Slack.
"""

import os
import re
import sys
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Add project root to path
WORKTREE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(WORKTREE_ROOT))

from src.tools import WebScraperTool, IndustryReportTool, OpportunityStorageTool
from src.tools.web_scraper_tool import RedditPostParser
from slack.slack_client import SlackClient, build_extraordinary_alert, build_daily_report, build_hustle_report
# ai_council imported lazily in consult_council to avoid loading crewai_tools at module level

OPPORTUNITY_STORE = Path.home() / ".claude" / "side_hustle_opportunities.json"
VAULT_ROOT = Path.home() / "srv" / "vault"

DEDUP_FILE = Path.home() / ".claude" / "hustle_seen_urls.json"
RETENTION_DAYS = 90


class DedupTracker:
    """Track seen URLs, skip duplicates within 90-day window."""

    def __init__(self, state_file: Optional[Path] = None):
        if state_file is None:
            self.state_file = DEDUP_FILE
        else:
            state_file = Path(state_file)
            self.state_file = state_file / "dedup.json" if state_file.is_dir() else state_file
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


def run_web_scan() -> list:
    """Scrape web for opportunities."""
    scraper = WebScraperTool()
    result = scraper._run(source="all")
    return result


def run_vault_check() -> str:
    """Check vault for industry trends."""
    tool = IndustryReportTool()
    return tool._run(query="market trend OR revenue OR demand OR opportunity")


def consult_council(opportunity: dict) -> dict:
    """Consult Coach with graceful degradation on failure."""
    try:
        from ai_council.src.agents.agents import CoachPartner
        coach = CoachPartner()
        prompt = f"""Evaluate this side hustle opportunity:

Title: {opportunity.get('title', '?')}
Description: {opportunity.get('description', '?')[:200]}
Income: €{opportunity.get('scores', {}).get('income', '?')}/month
Time: {opportunity.get('scores', {}).get('time_hrs_week', '?')} hrs/week
Startup cost: {opportunity.get('scores', {}).get('startup_cost', '?')}

Provide a one-line assessment of viability and one risk to watch."""
        coach_response = coach.evaluate(prompt)  # real LLM call
    except Exception:
        coach_response = None  # graceful fallback — build_rich_card handles None
    return {"coach": coach_response, "devils_advocate": ""}


def evaluate_opportunity(raw_text: str) -> list:
    """Parse scraped content into opportunity records.

    Format is: "[Source] title\n  description\n  URL: ..."
    Separated by double newlines (\n\n).
    """
    opportunities = []
    # Split on double newlines (output separator from scraper)
    sections = raw_text.split("\n\n")
    for section in sections:
        if not section.strip() or len(section) < 20:
            continue
        lines = section.strip().split("\n")
        if len(lines) < 1:
            continue

        # First line is [Source] Title
        first_line = lines[0]
        source = ""
        title = first_line

        if first_line.startswith("["):
            # Format: [SourceName] Title
            bracket_end = first_line.find("]")
            if bracket_end != -1:
                source = first_line[1:bracket_end]
                title = first_line[bracket_end + 1 :].strip()
                # Remove leading bracket artifact
                if title.startswith("["):
                    title = title[1:]
                    bracket_end2 = title.find("]")
                    if bracket_end2 != -1:
                        title = title[bracket_end2 + 1 :].strip()

        if not title or len(title) < 5:
            continue

        description = "\n".join(lines[:3])[:300]

        # Extract URL and income/time from HN Hiring output lines
        url = ""
        income = "?"
        time_hrs = "?"
        for line in lines:
            if "URL:" in line or "url:" in line or line.startswith("http"):
                url = line.split("URL:", 1)[-1].split("url:", 1)[-1].strip()
                if not url and line.startswith("http"):
                    url = line.strip()
            m_income = re.search(r'Income:\s*\$?([\d]+)', line)
            if m_income:
                income = m_income.group(1)
            m_time = re.search(r'Time:\s*(\d+)', line)
            if m_time:
                time_hrs = m_time.group(1)

        opp = {
            "id": str(uuid.uuid4()),
            "title": title,
            "description": description,
            "url": url,
            "scores": {
                "income": income,
                "time_hrs_week": time_hrs,
                "startup_cost": "low" if "remote" in description.lower() else "medium",
                "skill_match": "medium",
                "timing": "growing",
            },
            "council_feedback": {},
            "status": "pending",
            "discovered_date": datetime.now().strftime("%Y-%m-%d"),
            "source": source,
        }
        opportunities.append(opp)
    return opportunities


def is_extraordinary(opp: dict) -> bool:
    """Agent judgment: is this an extraordinary opportunity?"""
    try:
        income = int(str(opp.get("scores", {}).get("income", "0")).replace("?", "0").replace("€", "").replace(",", ""))
        time_hrs = int(str(opp.get("scores", {}).get("time_hrs_week", "99")).replace("?", "99").replace("<", "").split("-")[0])
        startup_cost_str = str(opp.get("scores", {}).get("startup_cost", "high"))
        startup_cost = 0 if startup_cost_str.lower() in ["low", "none", "€0", "0"] else 500

        # Extraordinary: high income potential + reasonable time + low startup
        if income >= 500 and time_hrs <= 15 and startup_cost <= 200:
            return True
    except Exception:
        pass
    return False


def save_opportunity(opp: dict) -> None:
    """Save opportunity to JSON store."""
    OPPORTUNITY_STORE.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if OPPORTUNITY_STORE.exists():
        try:
            existing = json.loads(OPPORTUNITY_STORE.read_text())
        except Exception:
            existing = []
    existing.append(opp)
    OPPORTUNITY_STORE.write_text(json.dumps(existing, indent=2))


def main():
    print(f"=== Side Hustle Daily Scan — {datetime.now().isoformat()} ===")

    # 1. Fetch web
    print("Scanning web sources...")
    try:
        web_results = run_web_scan()
    except Exception as e:
        print(f"Web scan failed: {e}")
        web_results = ""

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
        opp["summary"] = (
            RedditPostParser.extract_summary(opp.get("description", ""))
            if "Reddit" in opp.get("source", "")
            else opp.get("description", "")[:150]
        )
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


if __name__ == "__main__":
    main()