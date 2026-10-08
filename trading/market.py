"""Fetch real OHLC via yfinance (SQLite stores the rest)."""

from __future__ import annotations

import yfinance as yf


def _flatten_columns(data):
    if hasattr(data.columns, "levels") and data.columns.nlevels > 1:
        data = data.copy()
        data.columns = data.columns.get_level_values(0)
    return data


def fetch_ohlc(symbol: str, days: int = 90) -> list[dict]:
    period_days = max(days, 40)
    data = yf.download(
        symbol,
        period=f"{period_days}d",
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if data.empty:
        raise RuntimeError(f"No price data for {symbol}")
    data = _flatten_columns(data)

    rows = []
    for ts, row in data.dropna().iterrows():
        rows.append(
            {
                "time": ts.strftime("%Y-%m-%d"),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
            }
        )
    return rows


def fetch_closes(symbols: list[str], days: int = 90) -> dict:
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


def quote_board(symbols: list[str], days: int = 40) -> list[dict]:
    """Price + day change % for a list of tickers."""
    closes = fetch_closes(symbols, days=days)
    rows = []
    for sym, series in closes.items():
        if len(series) < 2:
            continue
        last = float(series.iloc[-1])
        prev = float(series.iloc[-2])
        change = last - prev
        pct = (change / prev * 100) if prev else 0.0
        week_ago = float(series.iloc[-6]) if len(series) >= 6 else prev
        week_pct = (last / week_ago - 1) * 100 if week_ago else 0.0
        rows.append(
            {
                "symbol": sym,
                "price": last,
                "change": change,
                "change_pct": pct,
                "week_pct": week_pct,
            }
        )
    rows.sort(key=lambda r: r["symbol"])
    return rows
