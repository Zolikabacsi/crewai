# CryptoFutures Research Agent — Design Spec

**Date:** 2026-04-29
**Author:** Claude (brainstorming)
**Status:** Draft

---

## Overview

A `CryptoFuturesResearchAgent` continuously monitors crypto and micro futures markets, surfaces matching strategy setups from a vault library, and delivers AI-synthesized briefings via Slack — daily at 08:00 and immediately on extraordinary signals.

It does NOT invent strategies. AI does the reading, monitoring, and synthesis. Strategy selection comes from a pre-built vault library. The agent is the researcher + router, not the strategist.

---

## Context

- **Goal:** Grow a €15–20K account aggressively via futures and crypto day-trading / short-term positions
- **Instruments:** BTC/ETH/alts perp futures (Binance), /MES and /MNQ micro futures (CME), altcoin leveraged swings
- **Experience:** Intermediate — knows the basics, wants AI to do the research and monitoring
- **Delivery:** Slack — daily briefing + on-demand + extraordinary alerts

---

## Agent: `CryptoFuturesResearchAgent`

### Role & Goal

- **Role:** Crypto & Futures Market Research Agent
- **Goal:** Monitor market conditions, surface matching setups from the strategy library, and deliver actionable briefings via Slack — enabling fast, informed trading decisions across multiple strategies in parallel.
- **Backstory:** You are a tireless quantitative research analyst who monitors on-chain data, funding rates, macro catalysts, and order flow across crypto and futures markets. You maintain a strategy library in the vault and match current market conditions to the best available setups. You report findings clearly and flag extraordinary signals immediately. Based in Europe, focused on EU market hours + 24h crypto.

### LLM

Same `get_llm()` as existing agents (MiniMax-M2.7 via custom endpoint at `https://chat.ultimateai.org`).

---

## Strategy Vault Library

Location: `~/srv/vault/crypto-futures-strategies/`

Five strategies, each as a markdown file with:
- Entry conditions (indicator-based, on-chain signal, timeframe)
- Exit rules (hard stop, trailing stop, time-based)
- Risk parameters (max position size, max leverage, daily loss limit)
- Optimal trading hours (UTC)
- Preferred pairs / contracts
- Recent performance notes (manual entry, updated weekly)

### Strategy 1: Momentum Breakout (Crypto Perp Scalping)

- **Instruments:** BTC, ETH, SOL perp futures (Binance)
- **Timeframe:** 15m – 1H
- **Entry:** Price breaks 4h high with volume spike >2x average + RSI >60
- **Exit:** 1.5x ATR trailing stop; max 4h hold
- **Risk:** Max 2% account per trade; leverage 3–5x only
- **Hours:** 08:00–16:00 UTC (peak EU/US overlap)
- **Notes:** Avoid around funding reset times (±30min)

### Strategy 2: Funding Rate Arbitrage Cycle

- **Instruments:** BTC, ETH perp futures (Binance)
- **Timeframe:** 4H – daily (swing)
- **Entry:** Funding rate turns negative (short squeeze setup) OR funding rate exceeds 0.1%/8h (top signal, go short)
- **Exit:** Funding rate normalizes OR 3% stop
- **Risk:** Max 3% account per trade; no leverage >5x
- **Hours:** Check every 8h (funding resets at 04:00, 12:00, 20:00 UTC)
- **Notes:** Most reliable on BTC/ETH. Avoid during high-vol events (CPI, FOMC weeks).

### Strategy 3: /MES Micro Futures Scalp

- **Instruments:** /MES (micro S&P 500 e-mini)
- **Timeframe:** 5m
- **Entry:** 9:30–10:30 UTC open range break + above/below VWAP
- **Exit:** 8pt stop; 16pt target; or 15min candle close below VWAP
- **Risk:** Max 1% account per trade; no overnight holds
- **Hours:** 09:30–16:00 UTC only (US market hours)
- **Notes:** Requires prop firm account or futures broker (Tradovate/TradingView). Not for crypto-only accounts.

### Strategy 4: Altcoin Leverage Swing

- **Instruments:** SOL, AVAX, LINK, or high-cap altcoin perps (Binance)
- **Timeframe:** 4H – daily
- **Entry:** BTC stabilizes after correction + altcoin starts outperforming BTC on 4H close; RSI(4H) < 60
- **Exit:** BTC breaks below关键支撑 OR 15% stop
- **Risk:** Max 2% account; leverage 3x max; size to 10% of account max per position
- **Hours:** Any; rebalance weekly
- **Notes:** More volatile than BTC/ETH — position sizing matters more than direction.

### Strategy 5: Macro Catalyst Gap Fill

- **Instruments:** BTC, ETH (cash index on CME), /MNQ
- **Timeframe:** Daily / event-driven
- **Entry:** Pre-announcement short/long depending on consensus; exit on actual vs expected surprise
- **Exit:** 2% stop on crypto; 30pt stop on /MNQ
- **Risk:** Max 4% account (high conviction play); not for beginners
- **Hours:** Align with economic calendar events
- **Notes:** Events: CPI, FOMC, NFP, ETF approval/decisions. Use economic calendar to pre-populate weekly watch list.

---

## Data Sources

| Source | API / Method | What it provides |
|---|---|---|
| Binance public API | `https://api.binance.com/api/v3/` | Funding rates, perp prices, 24h volume, order book |
| Binance Futures public API | `https://fapi.binance.com/fapi/v1/` | Futures funding rates, top trader long/short ratio |
| CoinGlass or equivalent | Web scraping or public endpoints | Liquidations, fear & greed, whale wallets |
| NewsAPI / CryptoPanct | REST API | Macro events, catalyst alerts |
| Economic calendar | Web scraping (Investing.com or similar) | CPI, FOMC, NFP dates |
| TradingView | Web scraper (Playwright) | Key technical levels, support/resistance |
| Existing Reddit/HN scraper | Already built | Sentiment, retail positioning |
| Vault | FS search | Strategy library, previous reports |

---

## Tools (5)

| Tool | Purpose |
|---|---|
| `BinanceFundingTool` | Fetch current funding rates for BTC/ETH/SOL perp futures |
| `BinanceMarketTool` | Fetch prices, volume, top-trader long/short ratio |
| `EconomicCalendarTool` | Get macro event dates for next 7 days |
| `VaultStrategyLibraryTool` | Read strategy files and match to current conditions |
| `CryptoSlackReporterTool` | Format and send Slack messages |

---

## Workflow: Daily Research Cycle

```
1. FETCH MARKET DATA (concurrent)
   - Binance funding rates (BTC, ETH, SOL)
   - Fear & greed index
   - BTC/ETH prices + volume
   - Economic calendar for next 48h

2. MATCH TO STRATEGY LIBRARY
   For each strategy, check if current conditions match:
   - Momentum Breakout: 4h high break? RSI level? Funding rate neutral?
   - Funding Arb: funding rate >0.1% or <0%?
   - /MES Scalp: within 09:30–10:30 UTC?
   - Altcoin Swing: BTC stabilizing? Altcoin outperforming?
   - Macro Catalyst: any high-impact events in 48h?

3. BUILD BRIEFING
   Synthesize findings — rank setups by urgency and fit
   Flag extraordinary signals: whale accumulation, unusual funding divergence,
   funding rate >0.15% (top signal), large liquidation cascade

4. SEND SLACK
   Format daily report → Slack webhook → #crypto-futures channel
   Immediate alert if extraordinary signal detected
```

---

## Slack Notifications

**Channel:** `#crypto-futures` (new channel to create)

**Daily Report — 08:00 UTC:**
```
📊 Crypto/Futures Research — <date>

⚡ TOP SETUPS TODAY:
  1. [Strategy Name] — <pair/contract> | <timeframe> | Risk: <Low/Med/High>
     Entry: <conditions> | Exit: <rules>
  2. [Strategy Name] — ...

🔭 MARKET CONTEXT:
  • BTC funding: <%+> | ETH funding: <%+> | SOL funding: <%+>
  • Fear & Greed: <n>/100
  • BTC price: $<...> | ETH price: $<...>
  • Key resistance: $<...> | Key support: $<...>
  • Catalysts next 48h: <event>, <event>

🎯 EXTRAORDINARY SIGNALS:
  • <signal description>

⚠️ RISK FLAGS:
  • <flag>
```

**Extraordinary Alert — immediate:**
```
🚨 SIGNAL: <signal type>
<Pair/Contract>: <...>
Details: <...>
Action: <long/short/watch>
Source: <data point>
```

---

## Scheduling

- **Daily report:** Cron at 08:00 UTC, durable, recurring
- **Midday check:** Cron at 13:00 UTC — funding rate reset check (send update if funding >0.1% or <0%)
- **Pre-market:** Cron at 09:00 UTC — /MES scalp setup check (only on US trading days)
- **On-demand:** Trigger with "scan crypto setups" → immediate full report

---

## File Structure

```
srv/crewai/src/
├── agents/
│   └── crypto_futures_research_agent.py   # New — CryptoFuturesResearchAgent
├── tools/
│   ├── binance_funding_tool.py             # New — fetch funding rates
│   ├── binance_market_tool.py              # New — fetch prices, OI, long/short
│   ├── economic_calendar_tool.py            # New — macro event calendar
│   └── crypto_slack_reporter_tool.py       # New — Slack formatting + sending
└── tasks/
    └── crypto_research_tasks.py            # New — task definitions

srv/crewai/scripts/
├── daily_crypto_research.py                # New — standalone daily script
└── send_crypto_alert.py                    # New — extraordinary alert script

srv/crewai/slack/
└── crypto_slack_client.py                  # New — separate client for crypto channel

vault/crypto-futures-strategies/             # New — strategy library
├── momentum-breakout.md
├── funding-rate-arbitrage.md
├── mes-micro-scalp.md
├── altcoin-lev-swing.md
└── macro-catalyst-gapping.md

.env (updates):
# Crypto/Futures channel
SLACK_CRYPTO_WEBHOOK_URL=<same incoming webhook, different channel>
```

---

## Dependencies

- Python: `requests`, `beautifulsoup4`, `playwright` (already installed)
- Binance: public API only (no API key needed for market data)
- Slack: incoming webhook (reuse existing hook, just post to different channel name)
- Vault: local FS (already configured)

---

## Edge Cases

- **Binance API rate limit:** Add 1s sleep between calls; cache results for 5min
- **Funding rate API unavailable:** Log warning, skip that signal, don't fail report
- **No matching setups:** Report says "No high-confidence setups today — stay patient"
- **Slack send fails:** Log locally; retry at next scheduled run
- **/MES requires futures broker:** Tool returns "Requires Tradovate/AMP account — broker not configured" if called without credentials
- **No extraordinary signals:** Send daily report only, no alert

---

## Scope Boundaries

- Research and monitoring only — no automated trading, no order execution
- No financial advice — agent surfaces research, user makes decisions
- All data from public APIs — no paid data subscriptions unless added later
- Crypto first; /MES futures can be added later when broker account is set up

---

## Related: /install-slack-app

Slack incoming webhooks used for notifications. Channel `#crypto-futures` to be created via Slack API or manually.

---