import pandas as pd

from .base import Signal, Strategy, register


@register
class MomentumStrategy(Strategy):
    key = "momentum"
    name = "Price Momentum"
    blurb = "Buy if price rose over N days, sell if it fell."
    lesson = (
        "Momentum assumes winners keep winning for a while. Compare today's close to "
        "the close N days ago: positive rate-of-change → buy bias; negative → sell. "
        "Simple, and it fails hard when trends reverse suddenly."
    )
    warmup = 15
    lookback = 10

    def signal_at(self, closes: pd.Series, i: int) -> Signal:
        if i < self.lookback + 1:
            return Signal.HOLD
        prev_roc = closes.iloc[i - 1] / closes.iloc[i - 1 - self.lookback] - 1
        cur_roc = closes.iloc[i] / closes.iloc[i - self.lookback] - 1
        if prev_roc <= 0 < cur_roc:
            return Signal.BUY
        if prev_roc >= 0 > cur_roc:
            return Signal.SELL
        return Signal.HOLD
