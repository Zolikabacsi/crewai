"""Slack formatting and sending for CryptoFutures research reports."""

import os
from datetime import datetime
import requests


class CryptoSlackClient:
    WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

    @classmethod
    def send(cls, message: str, channel: str = "#crypto-futures") -> str:
        if not cls.WEBHOOK_URL:
            return f"[Slack] No webhook — logged:\n{message}"
        try:
            resp = requests.post(cls.WEBHOOK_URL, json={"text": message}, timeout=15)
            return "Sent to Slack" if resp.status_code == 200 else f"Error: {resp.status_code}"
        except Exception as e:
            return f"[Slack] Failed: {e}"


def build_daily_report(
    funding_data: str,
    market_data: str,
    strategy_matches: str,
    macro_events: str,
    risk_flags: str = "",
    extraordinary: str = "",
) -> str:
    date = datetime.utcnow().strftime("%Y-%m-%d")
    sections = [
        f"📊 *Crypto/Futures Research — {date}*",
        "",
        "⚡ MARKET CONDITIONS:",
        funding_data,
        market_data,
        "",
        "🔭 STRATEGY MATCHES:",
        strategy_matches or "  No high-confidence setups today.",
        "",
        "📅 NEXT 48H CATALYSTS:",
        macro_events or "  No high-impact events.",
    ]
    if extraordinary:
        sections.extend(["", "🚨 EXTRAORDINARY SIGNALS:", extraordinary])
    if risk_flags:
        sections.extend(["", "⚠️ RISK FLAGS:", risk_flags])
    sections.append("\n_Research by CryptoFuturesResearchAgent_")
    return "\n".join(sections)


def build_extraordinary_alert(signal_type: str, details: str, action: str) -> str:
    return (
        f"🚨 *EXTRAORDINARY SIGNAL*\n"
        f"*Type:* {signal_type}\n"
        f"*Details:* {details}\n"
        f"*Suggested action:* {action}\n"
        f"_Sent immediately — review before acting_"
    )
