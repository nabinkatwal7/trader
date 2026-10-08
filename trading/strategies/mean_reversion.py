import pandas as pd

from .base import Signal, Strategy, register


@register
class MeanReversionStrategy(Strategy):
    key = "mean_reversion"
    name = "Z-Score Mean Reversion"
    blurb = "Buy when price is unusually far below its average, sell when far above."
    lesson = (
        "Z-score = (price − SMA) / stddev. A z of −2 means price is ~2σ cheap vs "
        "recent history — bet it snaps back. Opposite of momentum: you fade extremes "
        "instead of chasing them."
    )
    warmup = 25
    window = 20
    entry_z = 2.0

    def signal_at(self, closes: pd.Series, i: int) -> Signal:
        if i < self.window:
            return Signal.HOLD
        mid = closes.rolling(self.window).mean()
        std = closes.rolling(self.window).std()
        z = (closes - mid) / std.replace(0, pd.NA)
        prev, cur = z.iloc[i - 1], z.iloc[i]
        if pd.isna(prev) or pd.isna(cur):
            return Signal.HOLD
        if prev <= -self.entry_z < cur:  # recovering from deep cheap
            return Signal.BUY
        if prev >= self.entry_z > cur:  # rolling over from rich
            return Signal.SELL
        return Signal.HOLD
