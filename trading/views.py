import csv
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET, require_POST

from .analytics import allocation_rows, max_drawdown_pct, trade_stats
from .engine import (
    buy,
    get_or_create_portfolio,
    outcome_log,
    record_snapshot,
    run_backtest,
    run_tick,
    sell,
)
from .forms import (
    AlertForm,
    BacktestForm,
    BlotterFilterForm,
    CompareForm,
    JournalForm,
    LoginForm,
    ManualTradeForm,
    SettingsForm,
    SignUpForm,
    StrategySelectForm,
    WatchlistAddForm,
    WatchSymbolForm,
)
from .market import fetch_closes, fetch_ohlc, latest_prices, quote_board
from .models import BacktestResult, JournalEntry, PriceAlert, WatchlistItem
from .strategies import get_strategy, list_strategies


def _parse_symbols(raw: str) -> list[str]:
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def _check_alerts(portfolio, prices: dict[str, float]) -> list[str]:
    fired = []
    for alert in portfolio.alerts.filter(triggered=False):
        px = prices.get(alert.symbol)
        if px is None:
            continue
        hit = (alert.direction == "above" and px >= alert.target) or (
            alert.direction == "below" and px <= alert.target
        )
        if hit:
            alert.triggered = True
            alert.save(update_fields=["triggered"])
            fired.append(f"Alert: {alert.symbol} {alert.direction} ${alert.target:.2f} (now ${px:.2f})")
    return fired


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
    watched = list(portfolio.watchlist.values_list("symbol", flat=True)) or list(settings.DEFAULT_SYMBOLS)
    held = list(portfolio.positions.values_list("symbol", flat=True))
    price_symbols = sorted(set(watched) | set(held) | {portfolio.watch_symbol})
    prices: dict[str, float] = {}
    quotes = []
    price_error = None
    try:
        quotes = quote_board(price_symbols, days=40)
        prices = {q["symbol"]: q["price"] for q in quotes}
        for msg in _check_alerts(portfolio, prices):
            messages.warning(request, msg)
    except Exception as e:
        price_error = str(e)

    positions = []
    for pos in portfolio.positions.all():
        px = prices.get(pos.symbol)
        ur = pos.unrealized(px)
        positions.append(
            {
                "symbol": pos.symbol,
                "shares": pos.shares,
                "avg_cost": pos.avg_cost,
                "price": px,
                "value": (pos.shares * px) if px is not None else None,
                "unrealized": ur,
                "unrealized_pct": ((px / pos.avg_cost - 1) * 100) if px and pos.avg_cost else None,
            }
        )

    total = portfolio.total_value(prices) if prices else portfolio.cash
    strategy = get_strategy(portfolio.active_strategy)
    stats = trade_stats(list(portfolio.trades.all()))
    alloc = allocation_rows(list(portfolio.positions.all()), prices, portfolio.cash)
    return render(
        request,
        "trading/dashboard.html",
        {
            "portfolio": portfolio,
            "positions": positions,
            "total": total,
            "pnl": total - portfolio.starting_cash,
            "pnl_pct": ((total / portfolio.starting_cash) - 1) * 100 if portfolio.starting_cash else 0,
            "strategy": strategy,
            "strategy_form": StrategySelectForm(initial={"strategy": portfolio.active_strategy}),
            "trade_form": ManualTradeForm(initial={"symbol": portfolio.watch_symbol}),
            "watch_form": WatchSymbolForm(initial={"symbol": portfolio.watch_symbol}),
            "recent_trades": portfolio.trades.all()[:12],
            "price_error": price_error,
            "watch_price": prices.get(portfolio.watch_symbol),
            "quotes": quotes,
            "stats": stats,
            "alloc": alloc,
            "chart_days": portfolio.chart_range,
            "open_alerts": portfolio.alerts.filter(triggered=False).count(),
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
        sym = form.cleaned_data["symbol"].strip().upper()
        portfolio.watch_symbol = sym
        portfolio.save(update_fields=["watch_symbol", "updated_at"])
        WatchlistItem.objects.get_or_create(portfolio=portfolio, symbol=sym)
        if request.POST.get("range"):
            portfolio.chart_range = request.POST["range"]
            portfolio.save(update_fields=["chart_range", "updated_at"])
    return redirect("dashboard")


@login_required
@require_POST
def tick(request):
    portfolio = get_or_create_portfolio(request.user)
    try:
        fills, prices = run_tick(portfolio)
        for msg in _check_alerts(portfolio, prices):
            messages.warning(request, msg)
        if not fills:
            messages.info(request, "No signals this bar — holding.")
        else:
            for f in fills:
                extra = f" fee ${f.fee:.2f}" if f.fee else ""
                messages.success(request, f"{f.action} {f.shares:.4f} {f.symbol} @ ${f.price:.2f}{extra}")
    except Exception as e:
        messages.error(request, f"Tick failed: {e}")
    return redirect("dashboard")


@login_required
@require_POST
def reset_portfolio(request):
    portfolio = get_or_create_portfolio(request.user)
    portfolio.reset()
    record_snapshot(portfolio, note="reset")
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
    note = form.cleaned_data.get("note") or "manual"
    try:
        px = latest_prices(fetch_closes([symbol], days=5))[symbol]
    except Exception as e:
        messages.error(request, f"Price fetch failed: {e}")
        return redirect("dashboard")

    if action == "buy":
        fill = buy(portfolio, symbol, amount, px, note=note, strategy="manual")
        if fill:
            record_snapshot(portfolio, {symbol: px}, note="manual buy")
            messages.success(request, f"Bought {fill.shares:.4f} {symbol} @ ${px:.2f}")
        else:
            messages.error(request, f"Can't buy ${amount:.2f} (cash ${portfolio.cash:.2f})")
    else:
        fill = sell(portfolio, symbol, amount, px, note=note, strategy="manual")
        if fill:
            record_snapshot(portfolio, {symbol: px}, note="manual sell")
            pnl_bit = f" · realized ${fill.realized_pnl:+.2f}" if fill.realized_pnl is not None else ""
            messages.success(request, f"Sold {fill.shares:.4f} {symbol} @ ${px:.2f}{pnl_bit}")
        else:
            messages.error(request, f"Can't sell {amount} {symbol}")
    return redirect(request.POST.get("next") or "dashboard")


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
                max_drawdown_pct=outcome.max_drawdown_pct,
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
                f"({(outcome.ending_value / outcome.starting_cash - 1) * 100:+.1f}%) · "
                f"max DD {outcome.max_drawdown_pct:.1f}%",
            )
        except Exception as e:
            messages.error(request, f"Backtest failed: {e}")

    history = BacktestResult.objects.filter(user=request.user)[:12]
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
def compare_page(request):
    rows = []
    form = CompareForm(
        request.POST or None,
        initial={"strategies": ["sma_crossover", "buy_hold", "rsi"]},
    )
    if request.method == "POST" and form.is_valid():
        symbols = _parse_symbols(form.cleaned_data["symbols"])
        for key in form.cleaned_data["strategies"]:
            try:
                outcome = run_backtest(key, symbols, days=form.cleaned_data["days"], cash=form.cleaned_data["cash"])
                rows.append(
                    {
                        "key": key,
                        "name": get_strategy(key).name,
                        "ending": outcome.ending_value,
                        "pnl_pct": (outcome.ending_value / outcome.starting_cash - 1) * 100,
                        "trades": outcome.trade_count,
                        "dd": outcome.max_drawdown_pct,
                        "equity": outcome.equity,
                    }
                )
            except Exception as e:
                messages.error(request, f"{key}: {e}")
        rows.sort(key=lambda r: r["ending"], reverse=True)

    chart_json = json.dumps(
        [{"name": r["name"], "equity": r["equity"]} for r in rows]
    ) if rows else "null"
    return render(
        request,
        "trading/compare.html",
        {"form": form, "rows": rows, "chart_json": chart_json},
    )


@login_required
def markets_page(request):
    portfolio = get_or_create_portfolio(request.user)
    watched = list(portfolio.watchlist.values_list("symbol", flat=True))
    if not watched:
        watched = list(settings.DEFAULT_SYMBOLS)
    quotes = []
    error = None
    try:
        quotes = quote_board(watched, days=40)
        for msg in _check_alerts(portfolio, {q["symbol"]: q["price"] for q in quotes}):
            messages.warning(request, msg)
    except Exception as e:
        error = str(e)
    return render(
        request,
        "trading/markets.html",
        {
            "quotes": quotes,
            "error": error,
            "add_form": WatchlistAddForm(),
            "alert_form": AlertForm(),
            "alerts": portfolio.alerts.all()[:20],
            "watch_count": len(watched),
        },
    )


@login_required
@require_POST
def watchlist_add(request):
    portfolio = get_or_create_portfolio(request.user)
    form = WatchlistAddForm(request.POST)
    if form.is_valid():
        sym = form.cleaned_data["symbol"].strip().upper()
        WatchlistItem.objects.get_or_create(portfolio=portfolio, symbol=sym)
        messages.success(request, f"Added {sym} to watchlist")
    return redirect("markets")


@login_required
@require_POST
def watchlist_remove(request, symbol):
    portfolio = get_or_create_portfolio(request.user)
    WatchlistItem.objects.filter(portfolio=portfolio, symbol=symbol.upper()).delete()
    messages.info(request, f"Removed {symbol.upper()}")
    return redirect("markets")


@login_required
@require_POST
def alert_add(request):
    portfolio = get_or_create_portfolio(request.user)
    form = AlertForm(request.POST)
    if form.is_valid():
        PriceAlert.objects.create(
            portfolio=portfolio,
            symbol=form.cleaned_data["symbol"].upper(),
            direction=form.cleaned_data["direction"],
            target=form.cleaned_data["target"],
        )
        messages.success(request, "Alert created")
    return redirect("markets")


@login_required
@require_POST
def alert_delete(request, pk):
    portfolio = get_or_create_portfolio(request.user)
    PriceAlert.objects.filter(pk=pk, portfolio=portfolio).delete()
    return redirect("markets")


@login_required
def analytics_page(request):
    portfolio = get_or_create_portfolio(request.user)
    watched = list(portfolio.watchlist.values_list("symbol", flat=True)) or list(settings.DEFAULT_SYMBOLS)
    held = list(portfolio.positions.values_list("symbol", flat=True))
    prices = {}
    try:
        prices = latest_prices(fetch_closes(sorted(set(watched) | set(held)), days=40))
    except Exception:
        pass
    total = portfolio.total_value(prices) if prices else portfolio.cash
    trades = list(portfolio.trades.all())
    stats = trade_stats(trades)
    snaps = list(portfolio.snapshots.order_by("created_at").values("created_at", "equity")[:500])
    equity = [{"time": s["created_at"].strftime("%Y-%m-%d"), "value": s["equity"]} for s in snaps]
    # Deduplicate same-day keeping last
    by_day = {}
    for e in equity:
        by_day[e["time"]] = e
    equity = list(by_day.values())
    dd = max_drawdown_pct([e["value"] for e in equity]) if equity else 0.0
    alloc = allocation_rows(list(portfolio.positions.all()), prices, portfolio.cash)
    return render(
        request,
        "trading/analytics.html",
        {
            "portfolio": portfolio,
            "total": total,
            "pnl": total - portfolio.starting_cash,
            "stats": stats,
            "dd": dd,
            "alloc": alloc,
            "equity_json": json.dumps({"equity": equity, "starting": portfolio.starting_cash}),
            "positions": portfolio.positions.all(),
            "prices": prices,
        },
    )


@login_required
def blotter_page(request):
    portfolio = get_or_create_portfolio(request.user)
    form = BlotterFilterForm(request.GET or None)
    qs = portfolio.trades.all()
    if form.is_valid():
        if form.cleaned_data.get("symbol"):
            qs = qs.filter(symbol__iexact=form.cleaned_data["symbol"].strip())
        if form.cleaned_data.get("action"):
            qs = qs.filter(action=form.cleaned_data["action"])
    return render(
        request,
        "trading/blotter.html",
        {"trades": qs[:200], "form": form, "trade_form": ManualTradeForm()},
    )


@login_required
def export_trades(request):
    portfolio = get_or_create_portfolio(request.user)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="trades.csv"'
    writer = csv.writer(response)
    writer.writerow(["time", "action", "symbol", "shares", "price", "fee", "realized_pnl", "strategy", "note"])
    for t in portfolio.trades.order_by("created_at"):
        writer.writerow(
            [
                t.created_at.isoformat(),
                t.action,
                t.symbol,
                f"{t.shares:.6f}",
                f"{t.price:.4f}",
                f"{t.fee:.4f}",
                "" if t.realized_pnl is None else f"{t.realized_pnl:.4f}",
                t.strategy,
                t.note,
            ]
        )
    return response


@login_required
def journal_page(request):
    portfolio = get_or_create_portfolio(request.user)
    form = JournalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        JournalEntry.objects.create(
            portfolio=portfolio,
            title=form.cleaned_data["title"],
            body=form.cleaned_data["body"],
            symbol=form.cleaned_data["symbol"].upper(),
            mood=form.cleaned_data["mood"],
        )
        messages.success(request, "Journal entry saved")
        return redirect("journal")
    return render(
        request,
        "trading/journal.html",
        {"form": JournalForm(), "entries": portfolio.journal.all()[:50]},
    )


@login_required
@require_POST
def journal_delete(request, pk):
    portfolio = get_or_create_portfolio(request.user)
    JournalEntry.objects.filter(pk=pk, portfolio=portfolio).delete()
    return redirect("journal")


@login_required
def settings_page(request):
    portfolio = get_or_create_portfolio(request.user)
    form = SettingsForm(
        request.POST or None,
        initial={
            "fee_bps": portfolio.fee_bps,
            "starting_cash": portfolio.starting_cash,
            "active_strategy": portfolio.active_strategy,
            "chart_range": portfolio.chart_range,
        },
    )
    if request.method == "POST" and form.is_valid():
        portfolio.fee_bps = form.cleaned_data["fee_bps"]
        portfolio.starting_cash = form.cleaned_data["starting_cash"]
        portfolio.active_strategy = form.cleaned_data["active_strategy"]
        portfolio.chart_range = form.cleaned_data["chart_range"]
        portfolio.save()
        messages.success(request, "Settings saved")
        return redirect("settings")
    return render(request, "trading/settings.html", {"form": form, "portfolio": portfolio})


@login_required
def leaderboard_page(request):
    from django.contrib.auth.models import User

    board = []
    for u in User.objects.filter(portfolio__isnull=False).select_related("portfolio")[:50]:
        p = u.portfolio
        # Approximate equity with avg_cost mark if live prices unavailable per-user is expensive
        approx = p.cash + sum(pos.shares * pos.avg_cost for pos in p.positions.all())
        try:
            held = list(p.positions.values_list("symbol", flat=True))
            if held:
                px = latest_prices(fetch_closes(held, days=5))
                approx = p.total_value(px)
        except Exception:
            pass
        board.append(
            {
                "username": u.username,
                "equity": approx,
                "pnl_pct": (approx / p.starting_cash - 1) * 100 if p.starting_cash else 0,
                "trades": p.trades.count(),
                "strategy": p.active_strategy,
                "is_you": u.id == request.user.id,
            }
        )
    board.sort(key=lambda r: r["equity"], reverse=True)
    return render(request, "trading/leaderboard.html", {"board": board})


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
    last = candles[-1]["close"] if candles else None
    prev = candles[-2]["close"] if len(candles) > 1 else last
    return JsonResponse(
        {
            "symbol": symbol,
            "candles": candles,
            "markers": markers,
            "last": last,
            "change_pct": ((last / prev - 1) * 100) if last and prev else 0,
        }
    )


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
