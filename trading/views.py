import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET, require_POST

from .engine import (
    buy,
    get_or_create_portfolio,
    outcome_log,
    run_backtest,
    run_tick,
    sell,
    sell_all,
)
from .forms import (
    BacktestForm,
    LoginForm,
    ManualTradeForm,
    SignUpForm,
    StrategySelectForm,
    WatchSymbolForm,
)
from .market import fetch_closes, fetch_ohlc, latest_prices
from .models import BacktestResult
from .strategies import get_strategy, list_strategies


def _parse_symbols(raw: str) -> list[str]:
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


class UserLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class UserLogoutView(LogoutView):
    next_page = reverse_lazy("login")


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        get_or_create_portfolio(user)
        login(request, user)
        messages.success(request, f"Welcome, {user.username} — ${settings.STARTING_CASH:,.0f} paper cash ready.")
        return redirect("dashboard")
    return render(request, "registration/signup.html", {"form": form})


@login_required
def dashboard(request):
    portfolio = get_or_create_portfolio(request.user)
    symbols = list(settings.DEFAULT_SYMBOLS)
    held = list(portfolio.positions.values_list("symbol", flat=True))
    price_symbols = sorted(set(symbols) | set(held) | {portfolio.watch_symbol})
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
    watch_px = prices.get(portfolio.watch_symbol)
    return render(
        request,
        "trading/dashboard.html",
        {
            "portfolio": portfolio,
            "positions": positions,
            "prices": prices,
            "total": total,
            "pnl": total - portfolio.starting_cash,
            "pnl_pct": ((total / portfolio.starting_cash) - 1) * 100 if portfolio.starting_cash else 0,
            "strategy": strategy,
            "strategy_form": StrategySelectForm(initial={"strategy": portfolio.active_strategy}),
            "trade_form": ManualTradeForm(initial={"symbol": portfolio.watch_symbol}),
            "watch_form": WatchSymbolForm(initial={"symbol": portfolio.watch_symbol}),
            "recent_trades": portfolio.trades.all()[:20],
            "price_error": price_error,
            "watch_price": watch_px,
            "quote_rows": [
                {"symbol": s, "price": prices.get(s)} for s in settings.DEFAULT_SYMBOLS if s in prices
            ],
        },
    )


@login_required
@require_POST
def set_strategy(request):
    form = StrategySelectForm(request.POST)
    portfolio = get_or_create_portfolio(request.user)
    if form.is_valid():
        portfolio.active_strategy = form.cleaned_data["strategy"]
        portfolio.save(update_fields=["active_strategy", "updated_at"])
        messages.success(request, f"Active strategy → {get_strategy(portfolio.active_strategy).name}")
    return redirect("dashboard")


@login_required
@require_POST
def set_watch(request):
    form = WatchSymbolForm(request.POST)
    portfolio = get_or_create_portfolio(request.user)
    if form.is_valid():
        portfolio.watch_symbol = form.cleaned_data["symbol"].strip().upper()
        portfolio.save(update_fields=["watch_symbol", "updated_at"])
    return redirect("dashboard")


@login_required
@require_POST
def tick(request):
    portfolio = get_or_create_portfolio(request.user)
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


@login_required
@require_POST
def reset_portfolio(request):
    portfolio = get_or_create_portfolio(request.user)
    portfolio.reset()
    messages.warning(request, f"Portfolio reset to ${portfolio.starting_cash:,.2f}")
    return redirect("dashboard")


@login_required
@require_POST
def manual_trade(request):
    form = ManualTradeForm(request.POST)
    portfolio = get_or_create_portfolio(request.user)
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
        fill = sell(portfolio, symbol, amount, px, note="manual", strategy="manual")
        if fill:
            messages.success(request, f"Sold {fill.shares:.4f} {symbol} @ ${px:.2f}")
        else:
            messages.error(request, f"Can't sell {amount} {symbol}")
    return redirect("dashboard")


@login_required
def strategies_page(request):
    return render(request, "trading/strategies.html", {"strategies": list_strategies()})


@login_required
def backtest_page(request):
    result = None
    chart_payload = None
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
                user=request.user,
                strategy=outcome.strategy,
                symbols=",".join(outcome.symbols),
                days=outcome.days,
                starting_cash=outcome.starting_cash,
                ending_value=outcome.ending_value,
                trade_count=outcome.trade_count,
                log=outcome_log(outcome),
            )
            final_rows = [
                {
                    "symbol": sym,
                    "shares": shares,
                    "price": outcome.prices.get(sym),
                    "value": shares * outcome.prices.get(sym, 0.0),
                }
                for sym, shares in outcome.final_positions.items()
            ]
            chart_payload = {
                "equity": outcome.equity,
                "closes": outcome.primary_closes,
                "markers": outcome.markers,
                "primary": outcome.symbols[0],
                "starting": outcome.starting_cash,
            }
            result = {
                "outcome": outcome,
                "saved": saved,
                "strategy": get_strategy(outcome.strategy),
                "final_rows": final_rows,
            }
            messages.success(
                request,
                f"Backtest done: ${outcome.ending_value:,.2f} "
                f"({(outcome.ending_value / outcome.starting_cash - 1) * 100:+.1f}%)",
            )
        except Exception as e:
            messages.error(request, f"Backtest failed: {e}")

    history = BacktestResult.objects.filter(user=request.user)[:10]
    return render(
        request,
        "trading/backtest.html",
        {
            "form": form,
            "result": result,
            "history": history,
            "chart_json": json.dumps(chart_payload) if chart_payload else "null",
        },
    )


@login_required
@require_GET
def api_ohlc(request):
    symbol = (request.GET.get("symbol") or "AAPL").upper().strip()
    days = int(request.GET.get("days") or 90)
    days = max(30, min(days, 365))
    try:
        candles = fetch_ohlc(symbol, days=days)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

    portfolio = get_or_create_portfolio(request.user)
    markers = []
    for t in portfolio.trades.filter(symbol=symbol).order_by("created_at")[:100]:
        markers.append(
            {
                "time": t.created_at.strftime("%Y-%m-%d"),
                "position": "belowBar" if t.action == "BUY" else "aboveBar",
                "color": "#1a7a45" if t.action == "BUY" else "#b42318",
                "shape": "arrowUp" if t.action == "BUY" else "arrowDown",
                "text": t.action,
            }
        )
    return JsonResponse({"symbol": symbol, "candles": candles, "markers": markers})


@login_required
@require_GET
def api_backtest_chart(request, pk: int):
    bt = get_object_or_404(BacktestResult, pk=pk, user=request.user)
    try:
        data = json.loads(bt.log or "{}")
    except json.JSONDecodeError:
        data = {}
    return JsonResponse(
        {
            "equity": data.get("equity", []),
            "closes": data.get("primary_closes", []),
            "markers": data.get("markers", []),
            "primary": data.get("primary", ""),
            "starting": bt.starting_cash,
        }
    )
