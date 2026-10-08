from django.conf import settings
from django.db import models


class Portfolio(models.Model):
    """One simulated account per logged-in user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portfolio",
    )
    cash = models.FloatField(default=settings.STARTING_CASH)
    starting_cash = models.FloatField(default=settings.STARTING_CASH)
    active_strategy = models.CharField(max_length=64, default="sma_crossover")
    watch_symbol = models.CharField(max_length=16, default="AAPL")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} (${self.cash:.2f})"

    def position_value(self, prices: dict[str, float]) -> float:
        return sum(p.shares * prices.get(p.symbol, 0.0) for p in self.positions.all())

    def total_value(self, prices: dict[str, float]) -> float:
        return self.cash + self.position_value(prices)

    def reset(self):
        self.positions.all().delete()
        self.trades.all().delete()
        self.cash = self.starting_cash
        self.save()


class Position(models.Model):
    portfolio = models.ForeignKey(Portfolio, related_name="positions", on_delete=models.CASCADE)
    symbol = models.CharField(max_length=16)
    shares = models.FloatField(default=0.0)

    class Meta:
        unique_together = ("portfolio", "symbol")

    def __str__(self):
        return f"{self.shares:.4f} {self.symbol}"


class Trade(models.Model):
    BUY = "BUY"
    SELL = "SELL"
    ACTIONS = [(BUY, "Buy"), (SELL, "Sell")]

    portfolio = models.ForeignKey(Portfolio, related_name="trades", on_delete=models.CASCADE)
    action = models.CharField(max_length=4, choices=ACTIONS)
    symbol = models.CharField(max_length=16)
    shares = models.FloatField()
    price = models.FloatField()
    note = models.CharField(max_length=200, blank=True)
    strategy = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def notional(self) -> float:
        return self.shares * self.price


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
