"""Strategy registry — import side-effects register each strategy."""

from .base import Signal, Strategy, get_strategy, list_strategies
from . import (  # noqa: F401 — register
    buy_hold,
    sma_crossover,
    ema_crossover,
    rsi,
    macd,
    bollinger,
    momentum,
    mean_reversion,
)

__all__ = ["Signal", "Strategy", "get_strategy", "list_strategies"]
