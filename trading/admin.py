from django.contrib import admin

from .models import (
    BacktestResult,
    EquitySnapshot,
    JournalEntry,
    Portfolio,
    Position,
    PriceAlert,
    Trade,
    WatchlistItem,
)


class PositionInline(admin.TabularInline):
    model = Position
    extra = 0


class WatchlistInline(admin.TabularInline):
    model = WatchlistItem
    extra = 0


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ("user", "cash", "fee_bps", "active_strategy", "watch_symbol", "updated_at")
    inlines = [PositionInline, WatchlistInline]


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ("created_at", "portfolio", "action", "symbol", "shares", "price", "fee", "realized_pnl", "strategy")
    list_filter = ("action", "strategy")


@admin.register(BacktestResult)
class BacktestResultAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "strategy", "days", "ending_value", "max_drawdown_pct", "trade_count")


admin.site.register(JournalEntry)
admin.site.register(PriceAlert)
admin.site.register(EquitySnapshot)
