import pandas as pd

from .base import Signal, Strategy, register


@register
class EmaCrossover(Strategy):
    key = "ema_crossover"
    name = "EMA Crossover"
    blurb = "Like SMA crossover, but exponential averages react faster to new prices."
    lesson = (
        "An EMA weights recent prices more heavily than old ones, so it turns sooner "
        "than an SMA. Same golden/death cross idea — faster signal, more whipsaws."
    )
    warmup = 30
    short = 12
    long = 26

    def signal_at(self, closes: pd.Series, i: int) -> Signal:
        if i < self.long:
            return Signal.HOLD
        short_ma = closes.ewm(span=self.short, adjust=False).mean()
        long_ma = closes.ewm(span=self.long, adjust=False).mean()
        prev_s, prev_l = short_ma.iloc[i - 1], long_ma.iloc[i - 1]
        cur_s, cur_l = short_ma.iloc[i], long_ma.iloc[i]
        if prev_s <= prev_l and cur_s > cur_l:
            return Signal.BUY
        if prev_s >= prev_l and cur_s < cur_l:
            return Signal.SELL
        return Signal.HOLD
