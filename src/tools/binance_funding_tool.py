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
                url = "https://fapi.binance.com/fapi/v1/fundingRate"
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