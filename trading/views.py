from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .engine import (
    buy,
    get_or_create_portfolio,
    outcome_log,
    run_backtest,
    run_tick,
    sell,
    sell_all,
)
from .forms import BacktestForm, ManualTradeForm, StrategySelectForm
from .market import fetch_closes, latest_prices
from .models import BacktestResult
from .strategies import get_strategy, list_strategies


def _parse_symbols(raw: str) -> list[str]:
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def dashboard(request):
    portfolio = get_or_create_portfolio()
    symbols = list(settings.DEFAULT_SYMBOLS)
    # Include held symbols so we can price them
    held = list(portfolio.positions.values_list("symbol", flat=True))
    price_symbols = sorted(set(symbols) | set(held))
    prices: dict[str, float] = {}
    price_error = None
    try:
        prices = latest_prices(fetch_closes(price_symbols, days=40))
    except Exception as e:
        price_error = str(e)

    positions = []
    for pos in portfolio.positions.all():
        px = prices.get(pos.symbol)
        positions.append(
            {
                "symbol": pos.symbol,
                "shares": pos.shares,
                "price": px,
                "value": (pos.shares * px) if px is not None else None,
            }
        )

    total = portfolio.total_value(prices) if prices else portfolio.cash
    strategy = get_strategy(portfolio.active_strategy)
    return render(
        request,
        "trading/dashboard.html",
        {
            "portfolio": portfolio,
            "positions": positions,
            "prices": prices,
            "total": total,
            "pnl": total - portfolio.starting_cash,
            "strategy": strategy,
            "strategies": list_strategies(),
            "strategy_form": StrategySelectForm(initial={"strategy": portfolio.active_strategy}),
            "trade_form": ManualTradeForm(),
            "recent_trades": portfolio.trades.all()[:15],
            "price_error": price_error,
            "default_symbols": ",".join(settings.DEFAULT_SYMBOLS),
        },
    )


@require_POST
def set_strategy(request):
    form = StrategySelectForm(request.POST)
    portfolio = get_or_create_portfolio()
    if form.is_valid():
        portfolio.active_strategy = form.cleaned_data["strategy"]
        portfolio.save(update_fields=["active_strategy", "updated_at"])
        messages.success(request, f"Active strategy → {get_strategy(portfolio.active_strategy).name}")
    return redirect("dashboard")


@require_POST
def tick(request):
    portfolio = get_or_create_portfolio()
    try:
        fills, _ = run_tick(portfolio)
        if not fills:
            messages.info(request, "No signals this bar — holding.")
        else:
            for f in fills:
                messages.success(request, f"{f.action} {f.shares:.4f} {f.symbol} @ ${f.price:.2f}")
    except Exception as e:
        messages.error(request, f"Tick failed: {e}")
    return redirect("dashboard")


@require_POST
def reset_portfolio(request):
    portfolio = get_or_create_portfolio()
    portfolio.reset()
    messages.warning(request, f"Portfolio reset to ${portfolio.starting_cash:,.2f}")
    return redirect("dashboard")


@require_POST
def manual_trade(request):
    form = ManualTradeForm(request.POST)
    portfolio = get_or_create_portfolio()
    if not form.is_valid():
        messages.error(request, "Invalid trade.")
        return redirect("dashboard")
    symbol = form.cleaned_data["symbol"].upper()
    amount = form.cleaned_data["amount"]
    action = form.cleaned_data["action"]
    try:
        px = latest_prices(fetch_closes([symbol], days=5))[symbol]
    except Exception as e:
        messages.error(request, f"Price fetch failed: {e}")
        return redirect("dashboard")

    if action == "buy":
        fill = buy(portfolio, symbol, amount, px, note="manual", strategy="manual")
        if fill:
            messages.success(request, f"Bought {fill.shares:.4f} {symbol} @ ${px:.2f}")
        else:
            messages.error(request, f"Can't buy ${amount:.2f} (cash ${portfolio.cash:.2f})")
    else:
        if amount >= 1e9:  # ponytail: huge number means sell all from UI
            fill = sell_all(portfolio, symbol, px, note="manual", strategy="manual")
        else:
            fill = sell(portfolio, symbol, amount, px, note="manual", strategy="manual")
        if fill:
            messages.success(request, f"Sold {fill.shares:.4f} {symbol} @ ${px:.2f}")
        else:
            messages.error(request, f"Can't sell {amount} {symbol}")
    return redirect("dashboard")


def strategies_page(request):
    return render(request, "trading/strategies.html", {"strategies": list_strategies()})


def backtest_page(request):
    result = None
    form = BacktestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        symbols = _parse_symbols(form.cleaned_data["symbols"])
        try:
            outcome = run_backtest(
                form.cleaned_data["strategy"],
                symbols,
                days=form.cleaned_data["days"],
                cash=form.cleaned_data["cash"],
            )
            saved = BacktestResult.objects.create(
                strategy=outcome.strategy,
                symbols=",".join(outcome.symbols),
                days=outcome.days,
                starting_cash=outcome.starting_cash,
                ending_value=outcome.ending_value,
                trade_count=outcome.trade_count,
                log=outcome_log(outcome),
            )
            result = {"outcome": outcome, "saved": saved, "strategy": get_strategy(outcome.strategy)}
            messages.success(
                request,
                f"Backtest done: ${outcome.ending_value:,.2f} "
                f"({(outcome.ending_value / outcome.starting_cash - 1) * 100:+.1f}%)",
            )
        except Exception as e:
            messages.error(request, f"Backtest failed: {e}")

    history = BacktestResult.objects.all()[:10]
    return render(
        request,
        "trading/backtest.html",
        {
            "form": form,
            "result": result,
            "history": history,
            "strategies": list_strategies(),
        },
    )
