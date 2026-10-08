import pandas as pd

from .base import Signal, Strategy, register


@register
class SmaCrossover(Strategy):
    key = "sma_crossover"
    name = "SMA Crossover"
    blurb = "Buy when the fast average crosses above the slow average."
    lesson = (
        "A simple moving average (SMA) is the mean of the last N closing prices. "
        "When a short SMA crosses above a long SMA, short-term momentum is beating "
        "the longer trend — a classic 'golden cross' buy. The opposite is a sell."
    )
    warmup = 22
    short = 5
    long = 20

    def signal_at(self, closes: pd.Series, i: int) -> Signal:
        if i < self.long:
            return Signal.HOLD
        short_ma = closes.rolling(self.short).mean()
        long_ma = closes.rolling(self.long).mean()
        prev_s, prev_l = short_ma.iloc[i - 1], long_ma.iloc[i - 1]
        cur_s, cur_l = short_ma.iloc[i], long_ma.iloc[i]
        if pd.isna(prev_s) or pd.isna(prev_l) or pd.isna(cur_s) or pd.isna(cur_l):
            return Signal.HOLD
        if prev_s <= prev_l and cur_s > cur_l:
            return Signal.BUY
        if prev_s >= prev_l and cur_s < cur_l:
            return Signal.SELL
        return Signal.HOLD
