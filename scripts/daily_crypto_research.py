#!/usr/bin/env python3
"""Daily crypto/futures research — run via cron or on-demand.

Sequential: fetches market data, matches strategies, sends Slack.
No LLM calls — fast and reliable.
"""

import sys
from datetime import datetime
from pathlib import Path

# Resolve project root relative to this script
WORKTREE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(WORKTREE_ROOT))

from src.tools import (
    BinanceFundingTool,
    BinanceMarketTool,
    EconomicCalendarTool,
    VaultStrategyTool,
)
from slack.crypto_slack_client import (
    CryptoSlackClient,
    build_daily_report,
    build_extraordinary_alert,
)

# Conditions to check each run
CONDITIONS = [
    "funding_negative",
    "funding_positive",
    "breakout",
    "altcoin",
]


def is_extraordinary(funding: str, market: str) -> list[dict]:
    """Check if any extraordinary signals are present in market data."""
    signals = []

    # Check for extreme funding rates
    for line in funding.split("\n"):
        if "[BTC]" in line and ("TOP signal" in line or "SHORT squeeze" in line):
            signals.append({"type": "FUNDING_ALERT", "detail": line.strip(), "action": "review"})
        if "[ETH]" in line and ("TOP signal" in line or "SHORT squeeze" in line):
            signals.append({"type": "FUNDING_ALERT", "detail": line.strip(), "action": "review"})

    # Check for whale signals (L/S ratio extremes)
    for line in market.split("\n"):
        if "L/S Signal: LONG" in line and "HIGH volume" in line:
            signals.append({"type": "WHALE_BIAS", "detail": line.strip(), "action": "long bias confirmed"})
        if "L/S Signal: SHORT" in line and "HIGH volume" in line:
            signals.append({"type": "WHALE_BIAS", "detail": line.strip(), "action": "short bias confirmed"})

    return signals


def main():
    print(f"=== Crypto/Futures Research — {datetime.utcnow().isoformat()} ===")

    # 1. Fetch funding rates
    print("Fetching funding rates...")
    funding = BinanceFundingTool()._run("BTC,ETH,SOL")

    # 2. Fetch market data
    print("Fetching market data...")
    market = BinanceMarketTool()._run("BTC,ETH,SOL")

    # 3. Macro events
    print("Fetching macro calendar...")
    macro = EconomicCalendarTool()._run(days=2)

    # 4. Match strategies (sequential, no LLM)
    print("Matching strategies...")
    strategy_tool = VaultStrategyTool()
    matches = []
    for cond in CONDITIONS:
        match = strategy_tool._run("match", cond)
        if "[Strategy] No strategies" not in match and "No strategies found" not in match:
            matches.append(match)

    strategy_report = "\n\n".join(matches) if matches else ""

    # 5. Check for extraordinary signals
    extraordinary_signals = is_extraordinary(funding, market)
    extraordinary_text = ""
    for sig in extraordinary_signals:
        extraordinary_text += build_extraordinary_alert(
            sig["type"], sig["detail"], sig["action"]
        ) + "\n\n"

    # 6. Build and send Slack report
    print("Building Slack report...")
    report = build_daily_report(
        funding_data=funding,
        market_data=market,
        strategy_matches=strategy_report,
        macro_events=macro,
        risk_flags="",
        extraordinary=extraordinary_text.strip(),
    )
    result = CryptoSlackClient.send(report)
    print(f"Slack: {result}")

    # 7. Send extraordinary alerts immediately if any
    if extraordinary_signals:
        print(f"Sending {len(extraordinary_signals)} extraordinary alerts...")
        for sig in extraordinary_signals:
            alert = build_extraordinary_alert(sig["type"], sig["detail"], sig["action"])
            CryptoSlackClient.send(alert)

    print("Research complete.")


if __name__ == "__main__":
    main()
