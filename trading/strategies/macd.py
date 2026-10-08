import pandas as pd

from .base import Signal, Strategy, register


@register
class MacdStrategy(Strategy):
    key = "macd"
    name = "MACD Crossover"
    blurb = "Buy when the MACD line crosses above its signal line."
    lesson = (
        "MACD = fast EMA − slow EMA. A 'signal' line is an EMA of MACD. "
        "When MACD crosses above signal, momentum is turning up; below, turning down. "
        "It's a trend-following cousin of EMA crossover with an extra smoothing layer."
    )
    warmup = 40
    fast = 12
    slow = 26
    signal_span = 9

    def signal_at(self, closes: pd.Series, i: int) -> Signal:
        if i < self.slow + self.signal_span:
            return Signal.HOLD
        ema_fast = closes.ewm(span=self.fast, adjust=False).mean()
        ema_slow = closes.ewm(span=self.slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=self.signal_span, adjust=False).mean()
        prev_m, prev_s = macd.iloc[i - 1], signal.iloc[i - 1]
        cur_m, cur_s = macd.iloc[i], signal.iloc[i]
        if prev_m <= prev_s and cur_m > cur_s:
            return Signal.BUY
        if prev_m >= prev_s and cur_m < cur_s:
            return Signal.SELL
        return Signal.HOLD
