"""Slack client — send webhook notifications to Slack."""

import os
import json
import requests
from pathlib import Path


class SlackClient:
    WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
    CHANNEL = os.getenv("SLACK_CHANNEL", "#side-hustles")

    @classmethod
    def send(cls, message: str, webhook_url: str = "") -> str:
        url = webhook_url or cls.WEBHOOK_URL
        if not url:
            return f"[Slack] No webhook configured — logged locally:\n{message}"

        try:
            resp = requests.post(url, json={"text": message}, timeout=15)
            if resp.status_code == 200:
                return "Sent to Slack"
            return f"[Slack] Error: {resp.status_code} {resp.text}"
        except Exception as e:
            return f"[Slack] Failed: {e}"


def build_extraordinary_alert(title: str, description: str, scores: dict,
                               coach_says: str, devils_advocate: str, source: str) -> str:
    """Deprecated: unused. Kept for backwards compatibility with scripts that import it."""
    lines = [
        "🔔 *EXTRAORDINARY OPPORTUNITY FOUND*",
        "",
        f"*{title}*",
        description,
        "",
        f"💰 Income Potential: €{scores.get('income', '?')}/month",
        f"⏱ Time Required: {scores.get('time_hrs_week', '?')} hrs/week",
        f"💵 Startup Cost: €{scores.get('startup_cost', '?')}",
        f"🎯 Skill Match: {scores.get('skill_match', '?')}",
        f"📈 Market Timing: {scores.get('timing', '?')}",
        "",
        f"*Coach Says:* {coach_says}",
        f"*Devil's Advocate:* {devils_advocate}",
        "",
        "👉 _APPROVE (y/n) or INVESTIGATE FURTHER_",
        f"Source: {source}",
    ]
    return "\n".join(lines)


def build_daily_report(opportunities: list, date: str) -> str:
    lines = [
        f"📊 *Side Hustle Daily Report — {date}*",
        "",
        f"Found {len(opportunities)} opportunities today:",
        "",
    ]
    for i, opp in enumerate(opportunities, 1):
        lines.append(f"{i}. *{opp.get('title', '?')}* — €{opp.get('scores', {}).get('income', '?')}/mo | "
                     f"{opp.get('scores', {}).get('time_hrs_week', '?')} hrs/wk")
        coach = opp.get("council_feedback", {}).get("coach", "")
        if coach:
            lines.append(f"   Coach: {coach[:80]}")
    return "\n".join(lines)


from datetime import datetime

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