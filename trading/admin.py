from django.contrib import admin

from .models import BacktestResult, Portfolio, Position, Trade


class PositionInline(admin.TabularInline):
    model = Position
    extra = 0


class TradeInline(admin.TabularInline):
    model = Trade
    extra = 0
    readonly_fields = ("action", "symbol", "shares", "price", "note", "strategy", "created_at")


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ("user", "cash", "active_strategy", "watch_symbol", "updated_at")
    inlines = [PositionInline, TradeInline]


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ("created_at", "portfolio", "action", "symbol", "shares", "price", "strategy")
    list_filter = ("action", "strategy")


@admin.register(BacktestResult)
class BacktestResultAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "strategy", "days", "starting_cash", "ending_value", "trade_count")
