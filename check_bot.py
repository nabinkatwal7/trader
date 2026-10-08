"""Self-check for strategies + portfolio math. Run: .venv/Scripts/python check_bot.py"""

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import pandas as pd
from trading.strategies import Signal, get_strategy, list_strategies
from trading.strategies.rsi import rsi_series


def series(prices: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="B")
    return pd.Series(prices, index=idx, dtype=float)


def main() -> None:
    keys = {s.key for s in list_strategies()}
    expected = {
        "sma_crossover",
        "ema_crossover",
        "rsi",
        "macd",
        "bollinger",
        "momentum",
        "mean_reversion",
        "buy_hold",
    }
    assert expected <= keys, f"missing strategies: {expected - keys}"

    up = [100.0] * 20 + [101, 103, 106, 110, 115, 120, 126]
    down = [100.0] * 20 + [99, 97, 94, 90, 85, 80, 74]

    sma = get_strategy("sma_crossover")
    up_s, down_s = series(up), series(down)
    assert Signal.BUY in sma.signals(up_s), "uptrend should produce a BUY cross"
    assert Signal.SELL in sma.signals(down_s), "downtrend should produce a SELL cross"

    assert get_strategy("buy_hold").signal_at(series(up), 0) == Signal.BUY
    assert get_strategy("buy_hold").signal_at(series(up), 5) == Signal.HOLD

    r = rsi_series(series(list(range(50, 80)) + list(range(79, 40, -1))), 14)
    assert r.dropna().between(0, 100).all()

    print(f"check_bot: {len(keys)} strategies ok")


if __name__ == "__main__":
    main()
