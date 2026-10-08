import pandas as pd

from .base import Signal, Strategy, register


@register
class BollingerStrategy(Strategy):
    key = "bollinger"
    name = "Bollinger Bounce"
    blurb = "Buy near the lower band, sell near the upper band."
    lesson = (
        "Bollinger Bands = SMA ± (k × standard deviation). Price tagging the lower "
        "band can mean a stretch down (buy the bounce); the upper band a stretch up "
        "(sell). Works better in range-bound markets than strong trends."
    )
    warmup = 25
    window = 20
    k = 2.0

    def signal_at(self, closes: pd.Series, i: int) -> Signal:
        if i < self.window:
            return Signal.HOLD
        mid = closes.rolling(self.window).mean()
        std = closes.rolling(self.window).std()
        lower = mid - self.k * std
        upper = mid + self.k * std
        prev, cur = closes.iloc[i - 1], closes.iloc[i]
        prev_lo, cur_lo = lower.iloc[i - 1], lower.iloc[i]
        prev_hi, cur_hi = upper.iloc[i - 1], upper.iloc[i]
        if any(pd.isna(x) for x in (prev_lo, cur_lo, prev_hi, cur_hi)):
            return Signal.HOLD
        # Cross back above lower band → buy; cross back below upper → sell
        if prev <= prev_lo and cur > cur_lo:
            return Signal.BUY
        if prev >= prev_hi and cur < cur_hi:
            return Signal.SELL
        return Signal.HOLD
