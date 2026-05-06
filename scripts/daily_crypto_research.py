#!/usr/bin/env python3
"""Daily crypto/futures research — run via cron or on-demand.

Combines Binance, Bybit, Deribit options, Fear & Greed Index,
and Vault strategy matching. No LLM calls — fast and reliable.
"""

import json
import sys
import requests
from datetime import datetime
from pathlib import Path

WORKTREE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(WORKTREE_ROOT))

from src.tools import BinanceFundingTool, BinanceMarketTool, VaultStrategyTool
from slack.crypto_slack_client import (
    CryptoSlackClient,
    build_daily_report,
    build_extraordinary_alert,
)
from src.agent_logger import AgentLogger

# ── Additional symbols beyond the top-5 ──────────────────────────────────────
SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT"]

_HEADERS = {
    "User-Agent": "Mozilla/5.0 CryptoResearchBot/1.0",
    "Accept": "application/json",
}

# ── Fear & Greed Index ───────────────────────────────────────────────────────
def get_fear_greed() -> dict:
    """Fetch Fear & Greed Index from alternative.me."""
    try:
        resp = requests.get("https://api.alternative.me/fng/", timeout=10)
        if resp.status_code != 200:
            return {}
        data = resp.json()["data"][0]
        return {
            "value": int(data["value"]),
            "classification": data["value_classification"],
            "timestamp": data["timestamp"],
        }
    except Exception as e:
        return {}


# ── Bybit funding + OI ────────────────────────────────────────────────────────
def get_bybit_funding_batch(symbols: list[str]) -> dict[str, dict]:
    """Fetch Bybit perpetual funding rates for all symbols in ONE /tickers call.

    Bybit's /tickers endpoint returns current funding rate, next funding time,
    mark price, and open interest — all in one request, no per-symbol calls.
    """
    try:
        url = "https://api.bybit.com/v5/market/tickers"
        resp = requests.get(url, params={"category": "linear"}, headers=_HEADERS, timeout=15)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        if data.get("retCode") != 0:
            return {}
        out = {}
        for item in data["result"]["list"]:
            sym = item.get("symbol", "")
            # Match only USDT perpetuals in our symbol list
            base = sym.replace("USDT", "")
            if base not in symbols:
                continue
            rate_raw = item.get("fundingRate", "")
            if rate_raw == "":
                continue
            out[base] = {
                "rate": float(rate_raw) * 100,          # e.g. -0.0023%
                "next_funding_time": item.get("nextFundingTime", ""),
                "mark_price": item.get("markPrice", ""),
                "open_interest": item.get("openInterest", ""),
            }
        return out
    except Exception:
        return {}


def get_bybit_open_interest(symbol: str) -> dict:
    """Fetch Bybit open interest in USDT."""
    try:
        url = "https://api.bybit.com/v5/market/open-interest"
        params = {"category": "linear", "symbol": f"{symbol}USDT", "intervalTime": "1d", "limit": 1}
        resp = requests.get(url, params=params, headers=_HEADERS, timeout=10)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        if data.get("retCode") != 0:
            return {}
        result = data["result"]["list"]
        if not result:
            return {}
        oi = float(result[0]["openInterest"])
        return {"open_interest": oi, "symbol": symbol}
    except Exception:
        return {}


def get_bybit_long_short_ratio(symbol: str) -> dict:
    """Fetch Bybit top-trader long/short ratio."""
    try:
        url = "https://api.bybit.com/v5/market/account-ratio"
        params = {"category": "linear", "symbol": f"{symbol}USDT", "period": "1h", "limit": 5}
        resp = requests.get(url, params=params, headers=_HEADERS, timeout=10)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        if data.get("retCode") != 0:
            return {}
        result = data["result"]["list"]
        if not result:
            return {}
        latest = result[0]
        buy_ratio = float(latest.get("buyRatio", 0))
        sell_ratio = float(latest.get("sellRatio", 0))
        long_pct = round(buy_ratio * 100, 1)
        short_pct = round(sell_ratio * 100, 1)
        ls_ratio = round(buy_ratio / sell_ratio, 3) if sell_ratio else 0
        return {
            "long_pct": long_pct,
            "short_pct": short_pct,
            "ratio": ls_ratio,
        }
    except Exception:
        return {}


# ── CoinGlass liquidations ───────────────────────────────────────────────────
def get_liquidation_pressure(symbol: str) -> dict:
    """Estimate liquidation pressure from Bybit L/S ratio + OI change.

    Bybit's top-trader long/short ratio is the best free proxy for liquidation risk.
    A sharp drop in longAccountRatio = mass long liquidations occurring.
    """
    try:
        url = "https://api.bybit.com/v5/market/account-ratio"
        params = {"category": "linear", "symbol": f"{symbol}USDT", "period": "1h", "limit": 5}
        resp = requests.get(url, params=params, headers=_HEADERS, timeout=10)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        if data.get("retCode") != 0:
            return {}
        result = data["result"]["list"]
        if not result:
            return {}

        latest = result[0]
        prev = result[1] if len(result) > 1 else latest

        def ratio_float(r, field):
            v = r.get(field, "")
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0.0

        curr_buy = ratio_float(latest, "buyRatio")
        curr_long = curr_buy
        prev_buy = ratio_float(prev, "buyRatio")
        ratio_change = curr_long - prev_buy

        oi_data = get_bybit_open_interest(symbol)
        oi_usd = float(oi_data.get("open_interest_usd", 0))

        # Pressure classification
        if curr_long < 0.40:
            pressure = "EXTREME short bias — long squeeze risk HIGH"
        elif curr_long > 0.60:
            pressure = "EXTREME long bias — short squeeze risk HIGH"
        elif ratio_change < -0.05:
            pressure = f"Longs being liquidated (ratio dropped {ratio_change:.1%})"
        elif ratio_change > 0.05:
            pressure = f"Shorts being liquidated (ratio rose {ratio_change:.1%})"
        else:
            pressure = "NORMAL"

        return {
            "symbol": symbol,
            "long_ratio_pct": round(curr_long * 100, 1),
            "short_ratio_pct": round((1 - curr_long) * 100, 1),
            "ratio_change_1h": round(ratio_change * 100, 2),
            "oi_usd": oi_usd,
            "pressure": pressure,
        }
    except Exception:
        return {}


# ── Deribit options open interest ─────────────────────────────────────────────
def get_deribit_options_oi() -> dict:
    """Fetch total options open interest in USD from Deribit."""
    result = {}
    for currency in ["BTC", "ETH"]:
        try:
            url = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
            params = {"currency": currency, "kind": "option"}
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            if data.get("result"):
                items = data["result"]
                total_oi_usd = sum(float(i.get("open_interest", 0) or 0) for i in items)
                # open_interest is in the currency, convert to approximate USD using rough prices
                usd_multiplier = 95000 if currency == "BTC" else 2400
                total_oi_usd = total_oi_usd * usd_multiplier
                result[currency] = {"options_oi_usd_m": round(total_oi_usd / 1_000_000, 1)}
        except Exception:
            continue
    return result


# ── Cross-exchange funding comparison ───────────────────────────────────────
def compare_funding_rates(symbols: list[str]) -> list[dict]:
    """Compare Binance vs Bybit funding rates for all symbols in one shot."""
    binance_raw = BinanceFundingTool()._run(",".join(symbols))
    bybit_batch = get_bybit_funding_batch(symbols)
    if not bybit_batch:
        return []

    # Parse Binance output: [BTC] Funding: +0.012% | Signal: ...
    binance_rates = {}
    for line in binance_raw.split("\n"):
        for sym in symbols:
            if f"[{sym}]" in line and "Funding:" in line:
                try:
                    binance_rates[sym] = float(line.split("Funding:")[1].split("%")[0].strip())
                except Exception:
                    pass

    comparison = []
    for sym, bybit_data in bybit_batch.items():
        b_rate = binance_rates.get(sym)
        if b_rate is None:
            continue
        div = round(bybit_data["rate"] - b_rate, 4)
        comparison.append({
            "symbol": sym,
            "binance_rate": b_rate,
            "bybit_rate": bybit_data["rate"],
            "divergence": div,
        })
    return comparison


# ── Extraordinary signal detection ───────────────────────────────────────────
def detect_extraordinary_signals(
    fg_data: dict,
    funding_comparison: list[dict],
    liquidation_data: dict,
) -> list[dict]:
    """Detect high-conviction market signals."""
    signals = []

    # Fear & Greed extremes
    fg_value = fg_data.get("value")
    if fg_value is not None:
        if fg_value <= 15:
            signals.append({
                "type": "Extreme Fear",
                "detail": f"F&G at {fg_value}/100 — {fg_data['classification']}",
                "action": "Potential accumulation zone",
            })
        elif fg_value >= 90:
            signals.append({
                "type": "Extreme Greed",
                "detail": f"F&G at {fg_value}/100 — {fg_data['classification']}",
                "action": "Cautious / take profit zone",
            })

    # Large funding divergence between exchanges
    for comp in funding_comparison:
        if abs(comp["divergence"]) >= 0.05:  # 5bp divergence threshold
            direction = "Bybit higher (short squeeze risk)" if comp["divergence"] > 0 else "Binance higher (long squeeze risk)"
            signals.append({
                "type": f"Funding Divergence [{comp['symbol']}]",
                "detail": f"Binance {comp['binance_rate']:+.3f}% vs Bybit {comp['bybit_rate']:+.3f}% (Δ {comp['divergence']:+.4f}%)",
                "action": direction,
            })

    # Liquidation pressure extremes
    for sym, liq in liquidation_data.items():
        long_ratio = liq.get("long_ratio_pct", 0)
        if long_ratio <= 35 or long_ratio >= 65:
            direction = "EXTREME short bias" if long_ratio <= 35 else "EXTREME long bias"
            signals.append({
                "type": f"Liquidation Pressure [{sym}]",
                "detail": f"{direction}: {long_ratio:.0f}% long / {liq.get('short_ratio_pct', 0):.0f}% short",
                "action": "High risk of squeeze — do not enter against the bias",
            })

    return signals


# ── Build macro events ────────────────────────────────────────────────────────
_HIGH_IMPORTANCE = {"1"}  # Investing.com: 1=High, 2=Medium, 3=Low
_KEY_CURRENCIES = {"USD", "EUR", "GBP"}  # focus on macro drivers for crypto
# CFTC COT reports are weekly — real act/fcst only available on release day
_CFTC_KEYWORDS = {"CFTC"}
_IS_CFTC = lambda name: any(k in name for k in _CFTC_KEYWORDS)
_IMPORTANCE_LABEL = {"1": "🔴 High", "2": "🟠 Medium", "3": "🟡 Low"}


def get_economic_calendar() -> str:
    """Fetch economic events from Investing.com via embedded __NEXT_DATA__ JSON.

    No browser or API key needed — the full calendar is embedded server-side
    in the page HTML as a React hydration payload.
    """
    try:
        import re as _re

        resp = requests.get(
            "https://www.investing.com/economic-calendar",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=20,
        )
        if resp.status_code != 200:
            return "[Economic calendar unavailable]"

        # Extract embedded React state from __NEXT_DATA__
        match = _re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            resp.text,
            _re.DOTALL,
        )
        if not match:
            return "[Economic calendar unavailable]"

        state = json.loads(match.group(1))["props"]["pageProps"]["state"]
        ecal = state.get("economicCalendarStore", {})
        events_by_date: dict = ecal.get("calendarEventsByDate", {})

        if not events_by_date:
            return "[Economic calendar unavailable]"

        # Collect all events over the available window
        all_events = []
        for date_str, evlist in events_by_date.items():
            for ev in evlist:
                all_events.append({**ev, "date": date_str})

        # Filter: importance=1 AND USD/EUR/GBP AND type=event (skip holidays)
        filtered = [
            ev for ev in all_events
            if ev.get("importance") in _HIGH_IMPORTANCE
            and ev.get("currency") in _KEY_CURRENCIES
            and ev.get("type") == "event"
        ]

        if not filtered:
            return "[No high-impact USD/EUR/GBP events in window]"

        # Group CFTC events separately (weekly, only Prev available)
        cfct_events = [ev for ev in filtered if _IS_CFTC(ev.get("event", ""))]
        non_cfct_events = [ev for ev in filtered if not _IS_CFTC(ev.get("event", ""))]

        lines = ["*📅 Economic Calendar — High-Impact USD/EUR/GBP Events*", ""]

        # Non-CFTC events — grouped by currency + time
        if non_cfct_events:
            # Group by (currency, time_str)
            from collections import defaultdict
            by_ccy_time = defaultdict(list)
            for ev in non_cfct_events[:12]:
                raw_time = ev.get("time", "")
                try:
                    dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                    time_str = dt.strftime("%H:%M UTC")
                except Exception:
                    time_str = "All Day"
                key = (ev.get("currency", ""), time_str)
                by_ccy_time[key].append(ev)

            for (ccy, time_str), evs in sorted(by_ccy_time.items(), key=lambda x: x[0][1]):
                flag = {"USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧"}.get(ccy, ccy)
                lines.append(f"*{flag} {ccy} ({time_str})*")
                for ev in evs:
                    name = ev.get("event", "")[:55]
                    actual = ev.get("actual") or "—"
                    forecast = ev.get("forecast") or "—"
                    previous = ev.get("previous") or "—"
                    lines.append(
                        f"  • {name}\n"
                        f"    Act: {actual} | Fcst: {forecast} | Prev: {previous}"
                    )
                lines.append("")   # blank line after group

        # CFTC events — compact list with Prev only
        if cfct_events:
            raw_time = cfct_events[0].get("time", "")
            try:
                dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                cfct_time = dt.strftime("%H:%M UTC")
            except Exception:
                cfct_time = "19:30 UTC"
            lines.append(f"*🇺🇸 CFTC Commitment of Traders ({cfct_time})*")
            lines.append("_Weekly report — Act/Fcst posted after Friday release_")
            for ev in cfct_events[:10]:
                name = ev.get("event", "").replace("CFTC ", "").replace("speculative net positions", "Net Pos").replace("speculative ", "")
                prev = ev.get("previous") or "—"
                prev_str = f"Prev {prev}" if prev != "—" else ""
                direction = "📈 long" if prev not in ("—", "") and not prev.startswith("-") else "📉 short" if prev not in ("—", "") else ""
                lines.append(f"  • {name}: {prev_str} {direction}".strip())
            lines.append("")

        return "\n".join(lines)

    except Exception:
        return "[Economic calendar unavailable]"


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    task_name = f"daily_crypto_research_{datetime.date.today().isoformat()}"
    with AgentLogger(
        agent="crypto",
        task_name=task_name,
        vault_output_path=None,
    ) as run_log:
        run_log.step("run_start", {"task": task_name})

        # 1. Fear & Greed
        run_log.step("fetch_fear_greed")
        fg_data = get_fear_greed()
        fg_str = f"F&G: {fg_data['value']} ({fg_data['classification']})" if fg_data else "F&G: unavailable"
        print(f"  → {fg_str}")

        # 2. Binance funding
        run_log.step("fetch_binance_funding")
        funding = BinanceFundingTool()._run("BTC,ETH,SOL,BNB,XRP,DOGE,ADA,AVAX,LINK,DOT")
        print(f"  → {funding[:300]}")

        # 3. Bybit funding (batch — one API call for all symbols)
        run_log.step("fetch_bybit")
        bybit_batch = get_bybit_funding_batch(["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT"])
        bybit_lines = []
        for sym, data in bybit_batch.items():
            rate = data["rate"]
            signal = "SHORT squeeze" if rate < -0.01 else ("TOP signal" if rate > 0.1 else "Neutral")
            bybit_lines.append(f"[{sym}] Bybit Funding: {rate:+.3f}% | {signal}")
        bybit_str = "\n".join(bybit_lines) if bybit_lines else "[Bybit: no data]"
        print(f"  → {bybit_str}")

        # 4. Bybit OI
        run_log.step("fetch_bybit_oi")
        oi_data = {}
        for sym in ["BTC", "ETH", "SOL"]:
            oi = get_bybit_open_interest(sym)
            if oi:
                oi_data[sym] = oi
        oi_str = " | ".join(
            f"{sym} OI: ${oi.get('open_interest', 0):,.0f} USD"
            for sym, oi in oi_data.items()
        ) if oi_data else "[OI: unavailable]"
        print(f"  → {oi_str}")

        # 5. Long/Short ratios
        run_log.step("fetch_ls_ratios")
        ls_data = {}
        for sym in ["BTC", "ETH", "SOL"]:
            ls = get_bybit_long_short_ratio(sym)
            if ls:
                ls_data[sym] = ls
        ls_str = " | ".join(
            f"{sym} L/S: {ls['ratio']} ({ls['long_pct']}% long / {ls['short_pct']}% short)"
            for sym, ls in ls_data.items()
        ) if ls_data else "[L/S: unavailable]"
        print(f"  → {ls_str}")

        # 6. Liquidation pressure (Bybit L/S ratio — best free proxy)
        run_log.step("fetch_liquidation_pressure")
        liq_data = {}
        for sym in ["BTC", "ETH", "SOL"]:
            liq = get_liquidation_pressure(sym)
            if liq:
                liq_data[sym] = liq
        liq_str = " | ".join(
            f"{sym}: {liq.get('long_ratio_pct',0):.0f}%L/{liq.get('short_ratio_pct',0):.0f}%S | "
            f"{liq.get('pressure','')}"
            for sym, liq in liq_data.items()
        ) if liq_data else "[Liquidations: unavailable]"
        print(f"  → {liq_str}")

        # 7. Deribit options OI
        run_log.step("fetch_deribit_options")
        deribit_oi = get_deribit_options_oi()
        deribit_str = " | ".join(
            f"{cur} Options OI: ${oi['options_oi_usd_m']}M"
            for cur, oi in deribit_oi.items()
        ) if deribit_oi else "[Deribit: unavailable]"
        print(f"  → {deribit_str}")

        # 8. Cross-exchange funding comparison
        run_log.step("fetch_funding_rates")
        funding_comparison = compare_funding_rates(["BTC", "ETH", "SOL"])
        comp_str = "\n".join(
            f"  {c['symbol']}: Binance {c['binance_rate']:+.3f}% vs Bybit {c['bybit_rate']:+.3f}% (Δ {c['divergence']:+.4f}%)"
            for c in funding_comparison
        ) if funding_comparison else "[Comparison: no overlap]"
        print(f"  → {comp_str}")

        # 9. Macro calendar
        run_log.step("fetch_economic_calendar")
        macro = get_economic_calendar()
        print(f"  → {macro[:300]}")

        # 10. Vault strategy matching
        run_log.step("fetch_vault_strategies")
        strategy_report = VaultStrategyTool()._run(action="list", condition="funding")
        print(f"  → {strategy_report[:300]}")

        # 11. Market data (Binance)
        run_log.step("fetch_binance_market")
        market = BinanceMarketTool()._run("BTC,ETH,SOL,BNB,XRP")

        # 12. Extraordinary signals
        run_log.step("detect_extraordinary_signals")
        extraordinary_signals = detect_extraordinary_signals(fg_data, funding_comparison, liq_data)
        extraordinary_text = "\n".join(
            f"[{s['type']}] {s['detail']} → {s['action']}"
            for s in extraordinary_signals
        )
        if extraordinary_signals:
            print(f"  → {len(extraordinary_signals)} signals detected:")
            for s in extraordinary_signals:
                print(f"     [{s['type']}] {s['detail']}")

        # 13. Build and send Slack report
        run_log.step("build_report")
        # build_daily_report has a fixed 7-param signature — merge all data into existing fields
        funding_block = "\n".join(filter(None, [
            f"Fear & Greed: {fg_data['value']} ({fg_data['classification']})" if fg_data else None,
            funding,
            bybit_str if bybit_str != "[Bybit: no data]" else None,
        ]))

        market_block = "\n".join(filter(None, [
            market,
            oi_str if "unavailable" not in oi_str else None,
            ls_str if "unavailable" not in ls_str else None,
            deribit_str if "unavailable" not in deribit_str else None,
        ]))

        strategy_block = "\n".join(filter(None, [
            strategy_report if strategy_report and len(strategy_report) > 10 else None,
            f"Cross-exchange funding:\n{comp_str}" if comp_str != "[Comparison: no overlap]" else None,
        ]))

        risk_block = "\n".join(filter(None, [
            liq_str if liq_str != "[Liquidations: unavailable]" else None,
        ]))

        print("Building Slack report...")
        report = build_daily_report(
            funding_data=funding_block,
            market_data=market_block or market,
            strategy_matches=strategy_block or strategy_report or "No high-confidence setups today.",
            macro_events=macro if macro and len(macro) > 20 else "No high-impact events.",
            extraordinary=extraordinary_text.strip() if extraordinary_signals else "",
            risk_flags=risk_block,
        )

        # Record report output before sending
        run_log.capture_output({"report": report})

        # 14. Send Slack
        run_log.step("send_slack")
        result = CryptoSlackClient.send(report)
        print(f"Slack: {result}")

        # 15. Extraordinary alerts
        if extraordinary_signals:
            print(f"Sending {len(extraordinary_signals)} extraordinary alerts...")
            for sig in extraordinary_signals:
                alert = build_extraordinary_alert(sig["type"], sig["detail"], sig["action"])
                CryptoSlackClient.send(alert)

        print("Research complete.")
        run_log.finish(status="success", summary=f"Daily crypto research completed — Slack report sent.")


if __name__ == "__main__":
    main()
