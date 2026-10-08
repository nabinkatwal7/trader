"""Paper trading + backtest engine."""

from __future__ import annotations

import json
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from .analytics import max_drawdown_pct
from .market import fetch_closes, latest_prices
from .models import EquitySnapshot, Portfolio, Position, Trade, WatchlistItem
from .strategies import Signal, get_strategy


@dataclass
class Fill:
    action: str
    symbol: str
    shares: float
    price: float
    note: str = ""
    fee: float = 0.0
    realized_pnl: float | None = None


def get_or_create_portfolio(user) -> Portfolio:
    p, created = Portfolio.objects.get_or_create(
        user=user,
        defaults={
            "cash": settings.STARTING_CASH,
            "starting_cash": settings.STARTING_CASH,
            "active_strategy": "sma_crossover",
            "watch_symbol": settings.DEFAULT_SYMBOLS[0],
        },
    )
    if created:
        for sym in settings.DEFAULT_SYMBOLS:
            WatchlistItem.objects.get_or_create(portfolio=p, symbol=sym)
        record_snapshot(p, note="open")
    return p


def _fee(portfolio: Portfolio, notional: float) -> float:
    return abs(notional) * (portfolio.fee_bps / 10000.0)


def record_snapshot(portfolio: Portfolio, prices: dict[str, float] | None = None, note: str = "") -> EquitySnapshot:
    if prices is None:
        equity = portfolio.cash + sum(p.shares * p.avg_cost for p in portfolio.positions.all())
    else:
        equity = portfolio.total_value(prices)
    return EquitySnapshot.objects.create(
        portfolio=portfolio,
        equity=equity,
        cash=portfolio.cash,
        note=note,
    )


@transaction.atomic
def buy(portfolio: Portfolio, symbol: str, dollars: float, price: float, note: str = "", strategy: str = "") -> Fill | None:
    if price <= 0 or dollars <= 0:
        return None
    # Reserve fee from cash: spend at most `dollars` on shares+fee combined when possible
    fee_est = _fee(portfolio, dollars)
    spend = min(dollars, portfolio.cash)
    if spend <= fee_est + 0.01:
        return None
    notional = spend - fee_est if portfolio.fee_bps else spend
    fee = _fee(portfolio, notional)
    notional = spend - fee
    if notional <= 0 or spend > portfolio.cash + 1e-9:
        return None
    shares = notional / price
    portfolio.cash -= spend
    portfolio.save(update_fields=["cash", "updated_at"])
    pos, _ = Position.objects.get_or_create(
        portfolio=portfolio, symbol=symbol, defaults={"shares": 0.0, "avg_cost": 0.0}
    )
    new_shares = pos.shares + shares
    pos.avg_cost = ((pos.shares * pos.avg_cost) + notional) / new_shares if new_shares else price
    pos.shares = new_shares
    pos.save(update_fields=["shares", "avg_cost"])
    Trade.objects.create(
        portfolio=portfolio,
        action=Trade.BUY,
        symbol=symbol,
        shares=shares,
        price=price,
        fee=fee,
        note=note,
        strategy=strategy,
    )
    return Fill("BUY", symbol, shares, price, note, fee=fee)


@transaction.atomic
def sell(portfolio: Portfolio, symbol: str, shares: float, price: float, note: str = "", strategy: str = "") -> Fill | None:
    try:
        pos = Position.objects.get(portfolio=portfolio, symbol=symbol)
    except Position.DoesNotExist:
        return None
    if price <= 0 or shares <= 0 or shares > pos.shares + 1e-9:
        return None
    shares = min(shares, pos.shares)
    notional = shares * price
    fee = _fee(portfolio, notional)
    proceeds = notional - fee
    realized = (price - pos.avg_cost) * shares - fee
    portfolio.cash += proceeds
    portfolio.save(update_fields=["cash", "updated_at"])
    pos.shares -= shares
    if pos.shares < 1e-12:
        pos.delete()
    else:
        pos.save(update_fields=["shares"])
    Trade.objects.create(
        portfolio=portfolio,
        action=Trade.SELL,
        symbol=symbol,
        shares=shares,
        price=price,
        fee=fee,
        note=note,
        strategy=strategy,
        realized_pnl=realized,
    )
    return Fill("SELL", symbol, shares, price, note, fee=fee, realized_pnl=realized)


def sell_all(portfolio: Portfolio, symbol: str, price: float, note: str = "", strategy: str = "") -> Fill | None:
    try:
        pos = Position.objects.get(portfolio=portfolio, symbol=symbol)
    except Position.DoesNotExist:
        return None
    return sell(portfolio, symbol, pos.shares, price, note, strategy)


def apply_signals(portfolio: Portfolio, closes_map: dict, strategy_key: str, i: int | None = None) -> list[Fill]:
    strategy = get_strategy(strategy_key)
    fills: list[Fill] = []

    for sym, series in closes_map.items():
        idx = len(series) - 1 if i is None else i
        if idx < 0 or idx >= len(series):
            continue
        sig = strategy.signal_at(series, idx)
        price = float(series.iloc[idx])
        if sig == Signal.SELL:
            f = sell_all(portfolio, sym, price, note=f"{strategy.name} sell", strategy=strategy_key)
            if f:
                fills.append(f)

    portfolio.refresh_from_db()
    for sym, series in closes_map.items():
        idx = len(series) - 1 if i is None else i
        if idx < 0 or idx >= len(series):
            continue
        sig = strategy.signal_at(series, idx)
        price = float(series.iloc[idx])
        if sig == Signal.BUY and portfolio.cash > 1:
            fraction = 1.0 if strategy_key == "buy_hold" else settings.BUY_FRACTION
            budget = portfolio.cash * fraction
            f = buy(portfolio, sym, budget, price, note=f"{strategy.name} buy", strategy=strategy_key)
            if f:
                fills.append(f)
            portfolio.refresh_from_db()
    return fills


def run_tick(portfolio: Portfolio, symbols: list[str] | None = None) -> tuple[list[Fill], dict[str, float]]:
    if symbols is None:
        watched = list(portfolio.watchlist.values_list("symbol", flat=True))
        symbols = watched or list(settings.DEFAULT_SYMBOLS)
    closes = fetch_closes(symbols, days=90)
    fills = apply_signals(portfolio, closes, portfolio.active_strategy)
    prices = latest_prices(closes)
    record_snapshot(portfolio, prices, note="tick")
    return fills, prices


@dataclass
class BacktestOutcome:
    strategy: str
    symbols: list[str]
    days: int
    starting_cash: float
    ending_value: float
    trade_count: int
    events: list[dict]
    final_cash: float
    final_positions: dict[str, float]
    prices: dict[str, float]
    equity: list[dict]
    primary_closes: list[dict]
    markers: list[dict]
    max_drawdown_pct: float


def run_backtest(
    strategy_key: str,
    symbols: list[str],
    days: int = 90,
    cash: float = None,
) -> BacktestOutcome:
    cash = settings.STARTING_CASH if cash is None else cash
    strategy = get_strategy(strategy_key)
    closes = fetch_closes(symbols, days=days)

    dates = None
    for series in closes.values():
        dates = series.index if dates is None else dates.intersection(series.index)
    if dates is None or len(dates) < max(strategy.warmup, 5):
        raise RuntimeError("Not enough overlapping history to backtest.")

    aligned = {sym: closes[sym].loc[dates] for sym in closes}
    primary = list(aligned.keys())[0]
    sim_cash = cash
    positions: dict[str, float] = {}
    events: list[dict] = []
    equity: list[dict] = []
    markers: list[dict] = []

    def mark_to_market(day) -> float:
        px = {sym: float(s.loc[day]) for sym, s in aligned.items()}
        return sim_cash + sum(shares * px.get(sym, 0.0) for sym, shares in positions.items())

    def sim_buy(sym: str, dollars: float, price: float, day) -> None:
        nonlocal sim_cash
        if dollars <= 0 or dollars > sim_cash or price <= 0:
            return
        shares = dollars / price
        sim_cash -= dollars
        positions[sym] = positions.get(sym, 0.0) + shares
        events.append({"date": str(day.date()), "action": "BUY", "symbol": sym, "shares": shares, "price": price})
        if sym == primary:
            markers.append(
                {"time": str(day.date()), "position": "belowBar", "color": "#1a7a45", "shape": "arrowUp", "text": "BUY"}
            )

    def sim_sell_all(sym: str, price: float, day) -> None:
        nonlocal sim_cash
        held = positions.get(sym, 0.0)
        if held <= 0 or price <= 0:
            return
        sim_cash += held * price
        events.append({"date": str(day.date()), "action": "SELL", "symbol": sym, "shares": held, "price": price})
        positions.pop(sym, None)
        if sym == primary:
            markers.append(
                {"time": str(day.date()), "position": "aboveBar", "color": "#b42318", "shape": "arrowDown", "text": "SELL"}
            )

    for i in range(len(dates)):
        day = dates[i]
        for sym, series in aligned.items():
            if strategy.signal_at(series, i) == Signal.SELL and positions.get(sym, 0) > 0:
                sim_sell_all(sym, float(series.iloc[i]), day)
        for sym, series in aligned.items():
            if strategy.signal_at(series, i) == Signal.BUY and sim_cash > 1:
                fraction = 1.0 if strategy_key == "buy_hold" else settings.BUY_FRACTION
                sim_buy(sym, sim_cash * fraction, float(series.iloc[i]), day)
        equity.append({"time": str(day.date()), "value": round(mark_to_market(day), 2)})

    prices = {sym: float(s.iloc[-1]) for sym, s in aligned.items()}
    held_val = sum(shares * prices.get(sym, 0.0) for sym, shares in positions.items())
    ending = sim_cash + held_val
    primary_closes = [{"time": str(ts.date()), "value": float(v)} for ts, v in aligned[primary].items()]
    dd = max_drawdown_pct([e["value"] for e in equity])
    return BacktestOutcome(
        strategy=strategy_key,
        symbols=list(aligned.keys()),
        days=days,
        starting_cash=cash,
        ending_value=ending,
        trade_count=len(events),
        events=events,
        final_cash=sim_cash,
        final_positions=positions,
        prices=prices,
        equity=equity,
        primary_closes=primary_closes,
        markers=markers,
        max_drawdown_pct=dd,
    )


def outcome_log(outcome: BacktestOutcome) -> str:
    return json.dumps(
        {
            "events": outcome.events[-80:],
            "final_positions": outcome.final_positions,
            "final_cash": outcome.final_cash,
            "equity": outcome.equity,
            "primary_closes": outcome.primary_closes,
            "markers": outcome.markers,
            "primary": outcome.symbols[0] if outcome.symbols else "",
            "max_drawdown_pct": outcome.max_drawdown_pct,
        }
    )
