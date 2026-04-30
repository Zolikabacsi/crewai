"""Binance perpetual futures market data fetcher — no API key required."""

import requests
from crewai.tools import BaseTool


class BinanceMarketTool(BaseTool):
    name: str = "BinanceMarketTool"
    description: str = (
        "Fetch current market data for Binance perpetual futures. "
        "Pass symbols='BTC,ETH' (default: 'BTC'). "
        "Returns current price, 24h price change %, 24h volume in USDT, "
        "and long/short ratio from top traders. "
        "Source: Binance FAPI public endpoints."
    )

    def _run(self, symbols: str = "BTC,ETH") -> str:
        lines = []
        for symbol in [s.strip().upper() for s in symbols.split(",")]:
            try:
                symbol_pair = f"{symbol}USDT"

                # 1. 24h ticker: price, change %, volume
                ticker_url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
                ticker_resp = requests.get(ticker_url, params={"symbol": symbol_pair}, timeout=10)
                if ticker_resp.status_code != 200:
                    lines.append(f"[{symbol}] HTTP {ticker_resp.status_code} for ticker")
                    continue
                ticker = ticker_resp.json()

                price = float(ticker["lastPrice"])
                change_pct = float(ticker["priceChangePercent"])
                volume_usdt = float(ticker["quoteVolume"])

                # 2. Top trader long/short ratio
                ls_url = "https://fapi.binance.com/futures/data/topLongShortPositionRatio"
                ls_resp = requests.get(
                    ls_url,
                    params={"symbol": symbol_pair, "period": "1h", "limit": 1},
                    timeout=10,
                )
                long_short_ratio = None
                long_account_pct = None
                short_account_pct = None
                if ls_resp.status_code == 200:
                    ls_data = ls_resp.json()
                    if ls_data:
                        long_short_ratio = float(ls_data[0]["longShortRatio"])
                        long_account_pct = float(ls_data[0]["longAccount"]) * 100
                        short_account_pct = float(ls_data[0]["shortAccount"]) * 100

                # 3. Open interest
                oi_url = "https://fapi.binance.com/fapi/v1/openInterest"
                oi_resp = requests.get(oi_url, params={"symbol": symbol_pair}, timeout=10)
                open_interest = None
                if oi_resp.status_code == 200:
                    open_interest = float(oi_resp.json()["openInterest"])

                # 4. Funding rate (from premium index)
                prem_url = "https://fapi.binance.com/fapi/v1/premiumIndex"
                prem_resp = requests.get(prem_url, params={"symbol": symbol_pair}, timeout=10)
                funding_rate_pct = None
                if prem_resp.status_code == 200:
                    prem_data = prem_resp.json()
                    funding_rate_pct = float(prem_data["lastFundingRate"]) * 100

                # Build signal
                ls_signal = ""
                if long_short_ratio is not None:
                    if long_short_ratio > 1.2:
                        ls_signal = " | L/S Signal: LONG bias (top traders long)"
                    elif long_short_ratio < 0.8:
                        ls_signal = " | L/S Signal: SHORT bias (top traders short)"
                    else:
                        ls_signal = " | L/S Signal: NEUTRAL"

                # Volume signal
                vol_signal = ""
                if volume_usdt > 1_000_000_000:
                    vol_signal = " (HIGH volume)"

                parts = [
                    f"[{symbol}] Price: ${price:,.2f}",
                    f"| 24h Change: {change_pct:+.2f}%",
                    f"| 24h Vol: ${volume_usdt:,.0f} USDT{vol_signal}",
                ]
                if long_short_ratio is not None:
                    parts.append(
                        f"| Long/Short Ratio: {long_short_ratio:.2f}"
                        f" ({long_account_pct:.1f}% long / {short_account_pct:.1f}% short)"
                    )
                if funding_rate_pct is not None:
                    parts.append(f"| Funding Rate: {funding_rate_pct:+.4f}%")
                if open_interest is not None:
                    parts.append(f"| Open Interest: {open_interest:,.1f} {symbol}")

                parts.append(ls_signal)

                lines.append(" ".join(parts))

            except Exception as e:
                lines.append(f"[{symbol}] Error: {e}")

        return "\n".join(lines) if lines else "[Market] No data"
