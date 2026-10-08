"""Fetch real OHLC closes via yfinance."""

from __future__ import annotations

import yfinance as yf


def fetch_closes(symbols: list[str], days: int = 90) -> dict:
    """Return {symbol: pd.Series of adjusted Close}."""
    if not symbols:
        return {}
    period_days = max(days, 40)
    data = yf.download(
        symbols,
        period=f"{period_days}d",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    if data.empty:
        raise RuntimeError("No price data — check network or ticker symbols.")

    closes = {}
    if len(symbols) == 1:
        closes[symbols[0]] = data["Close"].dropna()
    else:
        for sym in symbols:
            if "Close" in data and sym in data["Close"].columns:
                series = data["Close"][sym].dropna()
                if len(series):
                    closes[sym] = series
    return closes


def latest_prices(closes_map: dict) -> dict[str, float]:
    return {sym: float(s.iloc[-1]) for sym, s in closes_map.items() if len(s)}
