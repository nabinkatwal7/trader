from django.conf import settings
from django.db import models


class Portfolio(models.Model):
    """One simulated account per logged-in user (SQLite-backed)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portfolio",
    )
    cash = models.FloatField(default=settings.STARTING_CASH)
    starting_cash = models.FloatField(default=settings.STARTING_CASH)
    active_strategy = models.CharField(max_length=64, default="sma_crossover")
    watch_symbol = models.CharField(max_length=16, default="AAPL")
    # Simulated commission in basis points of notional (10 = 0.10%)
    fee_bps = models.FloatField(default=0.0)
    chart_range = models.CharField(max_length=8, default="90")  # days as string
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} (${self.cash:.2f})"

    def position_value(self, prices: dict[str, float]) -> float:
        return sum(p.shares * prices.get(p.symbol, 0.0) for p in self.positions.all())

    def total_value(self, prices: dict[str, float]) -> float:
        return self.cash + self.position_value(prices)

    def invested_cost(self) -> float:
        return sum(p.shares * p.avg_cost for p in self.positions.all())

    def reset(self):
        self.positions.all().delete()
        self.trades.all().delete()
        self.snapshots.all().delete()
        self.cash = self.starting_cash
        self.save()


class Position(models.Model):
    portfolio = models.ForeignKey(Portfolio, related_name="positions", on_delete=models.CASCADE)
    symbol = models.CharField(max_length=16)
    shares = models.FloatField(default=0.0)
    avg_cost = models.FloatField(default=0.0)  # average entry price

    class Meta:
        unique_together = ("portfolio", "symbol")

    def __str__(self):
        return f"{self.shares:.4f} {self.symbol}"

    def unrealized(self, price: float | None) -> float | None:
        if price is None:
            return None
        return (price - self.avg_cost) * self.shares


class Trade(models.Model):
    BUY = "BUY"
    SELL = "SELL"
    ACTIONS = [(BUY, "Buy"), (SELL, "Sell")]

    portfolio = models.ForeignKey(Portfolio, related_name="trades", on_delete=models.CASCADE)
    action = models.CharField(max_length=4, choices=ACTIONS)
    symbol = models.CharField(max_length=16)
    shares = models.FloatField()
    price = models.FloatField()
    fee = models.FloatField(default=0.0)
    note = models.CharField(max_length=200, blank=True)
    strategy = models.CharField(max_length=64, blank=True)
    realized_pnl = models.FloatField(null=True, blank=True)  # set on sells
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def notional(self) -> float:
        return self.shares * self.price


class WatchlistItem(models.Model):
    portfolio = models.ForeignKey(Portfolio, related_name="watchlist", on_delete=models.CASCADE)
    symbol = models.CharField(max_length=16)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("portfolio", "symbol")
        ordering = ["symbol"]


class EquitySnapshot(models.Model):
    portfolio = models.ForeignKey(Portfolio, related_name="snapshots", on_delete=models.CASCADE)
    equity = models.FloatField()
    cash = models.FloatField()
    note = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class JournalEntry(models.Model):
    portfolio = models.ForeignKey(Portfolio, related_name="journal", on_delete=models.CASCADE)
    title = models.CharField(max_length=120)
    body = models.TextField()
    symbol = models.CharField(max_length=16, blank=True)
    mood = models.CharField(
        max_length=16,
        choices=[
            ("neutral", "Neutral"),
            ("confident", "Confident"),
            ("cautious", "Cautious"),
            ("fomo", "FOMO"),
            ("lesson", "Lesson learned"),
        ],
        default="neutral",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PriceAlert(models.Model):
    ABOVE = "above"
    BELOW = "below"
    portfolio = models.ForeignKey(Portfolio, related_name="alerts", on_delete=models.CASCADE)
    symbol = models.CharField(max_length=16)
    direction = models.CharField(max_length=8, choices=[(ABOVE, "Above"), (BELOW, "Below")])
    target = models.FloatField()
    triggered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class BacktestResult(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="backtests",
    )
    strategy = models.CharField(max_length=64)
    symbols = models.CharField(max_length=200)
    days = models.IntegerField()
    starting_cash = models.FloatField()
    ending_value = models.FloatField()
    trade_count = models.IntegerField(default=0)
    max_drawdown_pct = models.FloatField(default=0.0)
    log = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def pnl(self) -> float:
        return self.ending_value - self.starting_cash

    @property
    def pnl_pct(self) -> float:
        if self.starting_cash == 0:
            return 0.0
        return (self.ending_value / self.starting_cash - 1.0) * 100
