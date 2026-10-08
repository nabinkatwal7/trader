"""Minimal self-check — fake prices, no network. Run: python check_bot.py"""

from bot import Portfolio, signal_at, apply_signals
import pandas as pd


def fake_closes(prices: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="B")
    return pd.Series(prices, index=idx, dtype=float)


def main() -> None:
    # Flat then sharp uptrend → short MA should cross above long MA → BUY
    up = [100.0] * 20 + [101, 103, 106, 110, 115, 120, 126]
    series = fake_closes(up)
    sig = signal_at(series, len(series) - 1, short=5, long=20)
    assert sig == "BUY", f"expected BUY near uptrend cross, got {sig}"

    # Flat then sharp downtrend → SELL
    down = [100.0] * 20 + [99, 97, 94, 90, 85, 80, 74]
    series = fake_closes(down)
    sig = signal_at(series, len(series) - 1, short=5, long=20)
    assert sig == "SELL", f"expected SELL near downtrend cross, got {sig}"

    # Portfolio math
    p = Portfolio(cash=1000.0)
    t = p.buy("TEST", 500.0, 50.0)
    assert t is not None and abs(p.cash - 500) < 1e-9
    assert abs(p.positions["TEST"] - 10) < 1e-9
    t = p.sell_all("TEST", 60.0)
    assert t is not None and abs(p.cash - 1100) < 1e-9
    assert "TEST" not in p.positions

    # apply_signals buys on crossover with enough history
    p = Portfolio(cash=1000.0)
    closes = {"AAA": fake_closes(up)}
    trades = apply_signals(p, closes)
    assert any(t.action == "BUY" for t in trades), "strategy should buy on uptrend cross"
    assert p.cash < 1000

    print("check_bot: all ok")


if __name__ == "__main__":
    main()
