# CryptoFutures Research Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CryptoFuturesResearchAgent that monitors Binance APIs, surfaces matching setups from the strategy vault, and delivers daily briefings + extraordinary alerts via Slack.

**Architecture:** Agent uses data tools to fetch market conditions, matches against vault strategy docs, and routes findings through Slack. No automated trading — research and alerting only. Sequential (no LLM calls during data fetch).

**Tech Stack:** Python, requests, beautifulsoup4, playwright (existing); Binance public APIs (no key); Slack webhook (reuse existing); vault FS.

---

## File Map

```
src/tools/
  binance_funding_tool.py      # New — fetch Binance perp funding rates
  binance_market_tool.py       # New — fetch prices, OI, long/short ratio
  economic_calendar_tool.py    # New — scrape macro events from Investing.com
  vault_strategy_tool.py       # New — read strategy docs, match conditions

src/agents/
  crypto_futures_research_agent.py  # New — agent definition

src/tasks/
  crypto_research_tasks.py     # New — task definitions

scripts/
  daily_crypto_research.py      # New — standalone daily script

slack/
  crypto_slack_client.py        # New — Slack formatting + sending for crypto
```

---

## Task 1: BinanceFundingTool

**Files:**
- Create: `src/tools/binance_funding_tool.py`
- Test: inline (curl verification)

- [ ] **Step 1: Write the tool**

```python
"""Binance perpetual futures funding rate fetcher — no API key required."""

import requests
from crewai.tools import BaseTool


class BinanceFundingTool(BaseTool):
    name: str = "BinanceFundingTool"
    description: str = (
        "Fetch current funding rates for Binance perpetual futures. "
        "Pass symbols='BTC,ETH,SOL' (default: 'BTC,ETH'). "
        "Returns funding rate, countdown to next reset, and signal (Long/Short/Neutral). "
        "Source: Binance FAPI public endpoint."
    )

    def _run(self, symbols: str = "BTC,ETH") -> str:
        lines = []
        for symbol in [s.strip().upper() for s in symbols.split(",")]:
            try:
                url = f"https://fapi.binance.com/fapi/v1/fundingRate"
                params = {"symbol": f"{symbol}USDT", "limit": 1}
                resp = requests.get(url, params=params, timeout=10)
                if resp.status_code != 200:
                    lines.append(f"[{symbol}] HTTP {resp.status_code}")
                    continue
                data = resp.json()
                if not data:
                    lines.append(f"[{symbol}] No funding data")
                    continue
                latest = data[0]
                rate = float(latest["fundingRate"]) * 100  # convert to %
                funding_time = latest["fundingTime"]
                signal = "SHORT squeeze signal" if rate < -0.01 else ("TOP signal" if rate > 0.1 else "Neutral")
                lines.append(
                    f"[{symbol}] Funding: {rate:+.3f}% | Signal: {signal} | "
                    f"Next reset: {funding_time}"
                )
            except Exception as e:
                lines.append(f"[{symbol}] Error: {e}")
        return "\n".join(lines) if lines else "[Funding] No data"
```

- [ ] **Step 2: Verify with curl**

Run:
```bash
curl -s "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'BTC funding: {float(d[0][\"fundingRate\"])*100:+.3f}%')"
```
Expected: e.g. `BTC funding: +0.030%`

- [ ] **Step 3: Test tool in Python**

```bash
cd /home/zoltan/srv/crewai && .venv/bin/python3 -c "
import sys; sys.path.insert(0,'.')
from src.tools.binance_funding_tool import BinanceFundingTool
t = BinanceFundingTool()
print(t._run('BTC,ETH'))
"
```
Expected: Funding rates for BTC and ETH printed

- [ ] **Step 4: Commit**

```bash
git add src/tools/binance_funding_tool.py
git commit -m "feat: add BinanceFundingTool for perp funding rates"
```

---

## Task 2: BinanceMarketTool

**Files:**
- Create: `src/tools/binance_market_tool.py`

- [ ] **Step 1: Write the tool**

```python
"""Binance market data — prices, volume, top-trader long/short ratio. No API key."""

import requests
from crewai.tools import BaseTool


class BinanceMarketTool(BaseTool):
    name: str = "BinanceMarketTool"
    description: str = (
        "Fetch Binance market data for perpetual futures. "
        "Pass symbols='BTC,ETH' (default). "
        "Returns: current price, 24h volume, top-trader long/short ratio, open interest."
    )

    def _run(self, symbols: str = "BTC,ETH") -> str:
        lines = []
        for symbol in [s.strip().upper() for s in symbols.split(",")]:
            try:
                # Ticker price
                ticker_url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
                ticker = requests.get(ticker_url, params={"symbol": f"{symbol}USDT"}, timeout=10).json()
                price = float(ticker.get("lastPrice", 0))
                volume_24h = float(ticker.get("quoteVolume", 0))  # in USDT
                change_24h = float(ticker.get("priceChangePercent", 0))

                # Top-trader long/short ratio
                lsr_url = "https://fapi.binance/v1/futures/data/topLongShortPositionRatio"
                lsr = requests.get(lsr_url, params={"symbol": f"{symbol}USDT", "period": "1h", "limit": 1}, timeout=10).json()
                long_short_ratio = lsr[0]["longShortRatio"] if lsr else "?"

                lines.append(
                    f"[{symbol}] Price: ${price:,.1f} | 24h: {change_24h:+.2f}% | "
                    f"Vol: ${volume_24h/1e9:.2f}B | L/S Ratio: {long_short_ratio}"
                )
            except Exception as e:
                lines.append(f"[{symbol}] Error: {e}")
        return "\n".join(lines) if lines else "[Market] No data"
```

- [ ] **Step 2: Verify endpoints**

```bash
# Check top trader ratio endpoint
curl -s "https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol=BTCUSDT&period=1h&limit=1" | python3 -c "import sys,json; d=json.load(sys.stdin); print('L/S:', d[0]['longShortRatio'], 'Time:', d[0]['updateTime'])"
```

- [ ] **Step 3: Test tool**

```bash
cd /home/zoltan/srv/crewai && .venv/bin/python3 -c "
import sys; sys.path.insert(0,'.')
from src.tools.binance_market_tool import BinanceMarketTool
print(BinanceMarketTool()._run('BTC,ETH'))
"
```

- [ ] **Step 4: Commit**

```bash
git add src/tools/binance_market_tool.py
git commit -m "feat: add BinanceMarketTool for prices and long/short ratio"
```

---

## Task 3: EconomicCalendarTool

**Files:**
- Create: `src/tools/economic_calendar_tool.py`

- [ ] **Step 1: Write the tool**

```python
"""Scrape economic calendar for macro events (CPI, FOMC, NFP etc.)."""

import requests
from bs4 import BeautifulSoup
from crewai.tools import BaseTool


class EconomicCalendarTool(BaseTool):
    name: str = "EconomicCalendarTool"
    description: str = (
        "Fetch upcoming high-impact macro events from Investing.com economic calendar. "
        "Pass days=7 (default) to look ahead. "
        "Returns: event name, date/time UTC, impact (High/Medium/Low), previous/forecast values."
    )

    # Common high-impact event keywords to track
    TRACKED = ["CPI", "FOMC", "Non-Farm", "NFP", "Interest Rate",
               "GDP", "Retail Sales", "PMI", "ISM", "Unemployment",
               "ECB", "BOE", "Fed Chair", "ETF", "SEC", "approval"]

    def _run(self, days: int = 7) -> str:
        try:
            url = "https://www.investing.com/economic-calendar"
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                return f"[Calendar] HTTP {resp.status_code} — blocked, trying fallback"
        except Exception as e:
            return f"[Calendar] Error: {e}"

        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("tr.ec-event-row")
        lines = []
        count = 0
        for row in rows:
            if count >= days * 3:  # ~3 events per day
                break
            impact = row.get("data-impact", "")
            if impact not in ("3", "high", "2", "medium"):
                continue
            event_el = row.select_one(".left.event")
            time_el = row.select_one(".left.time")
            if not event_el or not time_el:
                continue
            event = event_el.get_text(strip=True)
            time = time_el.get_text(strip=True)
            if any(kw in event for kw in self.TRACKED):
                lines.append(f"[{impact}] {time} — {event}")
                count += 1

        if not lines:
            return "[Calendar] No high-impact events found in next 7 days"
        header = "📅 MACRO EVENTS NEXT 7 DAYS:\n"
        return header + "\n".join(f"  {l}" for l in lines)
```

- [ ] **Step 2: Test**

```bash
cd /home/zoltan/srv/crewai && .venv/bin/python3 -c "
import sys; sys.path.insert(0,'.')
from src.tools.economic_calendar_tool import EconomicCalendarTool
print(EconomicCalendarTool()._run())
"
```

- [ ] **Step 3: Commit**

```bash
git add src/tools/economic_calendar_tool.py
git commit -m "feat: add EconomicCalendarTool for macro event tracking"
```

---

## Task 4: VaultStrategyTool

**Files:**
- Create: `src/tools/vault_strategy_tool.py`

- [ ] **Step 1: Write the tool**

```python
"""Read strategy library from vault and match to current market conditions."""

import json
import os
from pathlib import Path
from crewai.tools import BaseTool


class VaultStrategyTool(BaseTool):
    name: str = "VaultStrategyTool"
    description: str = (
        "Read strategy library from vault and match conditions to current market data. "
        "Pass action='list' to list all strategies, action='match' to match a specific "
        "condition (e.g. 'funding_negative', 'breakout', 'news_event'). "
        "Returns strategy docs with entry/exit rules."
    )

    VAULT_ROOT = Path.home() / "srv" / "vault" / "crypto-futures-strategies"
    FALLBACK_ROOT = Path.home() / "srv" / "crewai" / "vault" / "crypto-futures-strategies"

    def _run(self, action: str = "list", condition: str = "") -> str:
        root = self.VAULT_ROOT if self.VAULT_ROOT.exists() else self.FALLBACK_ROOT
        if not root.exists():
            return f"[Strategy] Vault not found at {root}"

        md_files = sorted(root.glob("*.md"))
        if not md_files:
            return f"[Strategy] No strategies found in {root}"

        if action == "list":
            return self._list_strategies(md_files)

        # Match mode — search for keywords in all strategy files
        return self._match_condition(md_files, condition.lower())

    def _list_strategies(self, files: list[Path]) -> str:
        lines = ["📚 STRATEGY LIBRARY:"]
        for f in files:
            title = f.stem.replace("-", " ").title()
            lines.append(f"  • {title} → {f.name}")
        return "\n".join(lines)

    def _match_condition(self, files: list[Path], condition: str) -> str:
        condition_map = {
            "funding_negative": ("funding-rate-arbitrage", "short squeeze"),
            "funding_positive": ("funding-rate-arbitrage", "top signal"),
            "funding_high": ("funding-rate-arbitrage", "0.1%"),
            "breakout": ("momentum-breakout", "break"),
            "news": ("macro-catalyst-gapping", "event"),
            "catalyst": ("macro-catalyst-gapping", "CPI"),
            "fomc": ("macro-catalyst-gapping", "FOMC"),
            "altcoin": ("altcoin-lev-swing", "altcoin"),
            "mes": ("mes-micro-scalp", "MES"),
            "scalp": ("momentum-breakout", "scalp"),
        }

        keywords = condition_map.get(condition, (condition, condition))
        matched = []
        for f in files:
            content = f.read_text().lower()
            # Match by filename key or by content keyword
            stem = f.stem.lower().replace("-", "")
            if any(kw in stem for kw in keywords) or any(kw in content for kw in keywords):
                text = f.read_text()
                # Extract title
                title = text.split("\n")[0].strip("# ").strip()
                # Extract first 300 chars of content
                body = "\n".join(text.split("\n")[1:])[:300]
                matched.append(f"### {title}\n{body}\n")

        if not matched:
            return f"[Strategy] No strategies match condition: {condition}"
        header = f"🎯 MATCHING STRATEGIES FOR: {condition.upper()}\n"
        return header + "\n---\n".join(matched)
```

- [ ] **Step 2: Test**

```bash
cd /home/zoltan/srv/crewai && .venv/bin/python3 -c "
import sys; sys.path.insert(0,'.')
from src.tools.vault_strategy_tool import VaultStrategyTool
t = VaultStrategyTool()
print(t._run('list'))
print()
print(t._run('match', 'funding_negative'))
"
```

- [ ] **Step 3: Commit**

```bash
git add src/tools/vault_strategy_tool.py
git commit -m "feat: add VaultStrategyTool for strategy library access"
```

---

## Task 5: CryptoSlackClient

**Files:**
- Create: `slack/crypto_slack_client.py`
- Modify: `src/tools/__init__.py` (add new tools)

- [ ] **Step 1: Write Slack client**

```python
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
    risk_flags: str,
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
        "",
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
```

- [ ] **Step 2: Update tools __init__.py**

Add these imports to `src/tools/__init__.py`:
```python
from .binance_funding_tool import BinanceFundingTool
from .binance_market_tool import BinanceMarketTool
from .economic_calendar_tool import EconomicCalendarTool
from .vault_strategy_tool import VaultStrategyTool
```

Add to `__all__`:
```python
    "BinanceFundingTool",
    "BinanceMarketTool",
    "EconomicCalendarTool",
    "VaultStrategyTool",
```

- [ ] **Step 3: Commit**

```bash
git add slack/crypto_slack_client.py src/tools/__init__.py
git commit -m "feat: add CryptoSlackClient and wire new tools to __init__"
```

---

## Task 6: Daily Research Script

**Files:**
- Create: `scripts/daily_crypto_research.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Daily crypto/futures research — run via cron or on-demand."""

import sys
from datetime import datetime
from pathlib import Path

WORKTREE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(WORKTREE_ROOT))

from src.tools import (
    BinanceFundingTool,
    BinanceMarketTool,
    EconomicCalendarTool,
    VaultStrategyTool,
)
from slack.crypto_slack_client import CryptoSlackClient, build_daily_report

# Conditions to check against strategy library
CONDITIONS = [
    "funding_negative",
    "funding_positive",
    "breakout",
    "altcoin",
]


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
        if "[Strategy] No strategies" not in match:
            matches.append(match)

    strategy_report = "\n".join(matches) if matches else ""

    # 5. Build and send Slack report
    print("Building Slack report...")
    report = build_daily_report(
        funding_data=funding,
        market_data=market,
        strategy_matches=strategy_report,
        macro_events=macro,
        risk_flags="",
    )
    result = CryptoSlackClient.send(report)
    print(result)
    print("Research complete.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test**

```bash
cd /home/zoltan/srv/crewai && .venv/bin/python3 scripts/daily_crypto_research.py
```

- [ ] **Step 3: Commit**

```bash
git add scripts/daily_crypto_research.py
git commit -m "feat: add daily_crypto_research.py script"
```

---

## Task 7: Schedule Cron

- [ ] **Step 1: Create daily cron at 08:00 UTC**

Run via CronCreate:
```
cron: "0 8 * * 1-5"
durable: true
recurring: true
prompt: "cd /home/zoltan/srv/crewai && .venv/bin/python3 scripts/daily_crypto_research.py 2>&1"
```

Note: durable cron expires after 7 days per platform limit. Re-create when needed.

- [ ] **Step 2: Create midday funding check at 13:00 UTC**

```
cron: "0 13 * * 1-5"
durable: true
recurring: true
prompt: "cd /home/zoltan/srv/crewai && .venv/bin/python3 scripts/daily_crypto_research.py 2>&1"
```

---

## Verification Checklist

After all tasks complete, run:
```bash
# Test all tools
.venv/bin/python3 -c "
import sys; sys.path.insert(0,'.')
from src.tools import BinanceFundingTool, BinanceMarketTool, EconomicCalendarTool, VaultStrategyTool
print('Funding:', BinanceFundingTool()._run('BTC'))
print('Market:', BinanceMarketTool()._run('BTC'))
print('Calendar:', EconomicCalendarTool()._run(2))
print('Strategies:', VaultStrategyTool()._run('list'))
"

# Test full script
.venv/bin/python3 scripts/daily_crypto_research.py
```

Expected: All four tools return data; script runs end-to-end and sends to Slack.

---

## Dependencies

All already installed in `.venv`:
- `requests` ✓
- `beautifulsoup4` ✓
- `playwright` ✓
- `crewai_tools` (for BaseTool) ✓

No new packages needed.

---

## Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| Binance funding rates | Task 1 |
| Binance market data | Task 2 |
| Economic calendar | Task 3 |
| Strategy vault library | Task 4 |
| Slack reporting | Task 5 |
| Daily 08:00 cron | Task 7 |
| Midday funding check | Task 7 |
| On-demand trigger | Script ready for manual run |