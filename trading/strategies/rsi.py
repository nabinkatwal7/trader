import pandas as pd

from .base import Signal, Strategy, register


def rsi_series(closes: pd.Series, period: int = 14) -> pd.Series:
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


@register
class RsiStrategy(Strategy):
    key = "rsi"
    name = "RSI Mean Reversion"
    blurb = "Buy when RSI is oversold (<30), sell when overbought (>70)."
    lesson = (
        "RSI (Relative Strength Index) measures how hard price has run up or down "
        "lately, scaled 0–100. Below 30 often means 'oversold' (possible bounce); "
        "above 70 'overbought' (possible pullback). It bets on reversion, not trend."
    )
    warmup = 20
    period = 14
    low = 30
    high = 70

    def signal_at(self, closes: pd.Series, i: int) -> Signal:
        if i < self.period + 1:
            return Signal.HOLD
        rsi = rsi_series(closes, self.period)
        prev, cur = rsi.iloc[i - 1], rsi.iloc[i]
        if pd.isna(prev) or pd.isna(cur):
            return Signal.HOLD
        # Cross back up through oversold → buy; cross down through overbought → sell
        if prev < self.low <= cur:
            return Signal.BUY
        if prev > self.high >= cur:
            return Signal.SELL
        return Signal.HOLD
