import pandas as pd

from .base import Signal, Strategy, register


@register
class BuyAndHold(Strategy):
    key = "buy_hold"
    name = "Buy & Hold"
    blurb = "Buy once at the start, never sell. The baseline every strategy must beat."
    lesson = (
        "Buy & hold skips timing entirely. In backtests it's the benchmark: if your "
        "fancy strategy can't beat doing nothing, complexity isn't helping."
    )
    warmup = 1

    def signal_at(self, closes: pd.Series, i: int) -> Signal:
        # First actionable bar only — engine buys with available cash once
        if i == 0:
            return Signal.BUY
        return Signal.HOLD
