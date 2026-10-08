"""Paper trading + backtest engine."""

from __future__ import annotations

import json
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from .market import fetch_closes, latest_prices
from .models import Portfolio, Position, Trade
from .strategies import Signal, get_strategy


@dataclass
class Fill:
    action: str
    symbol: str
    shares: float
    price: float
    note: str = ""


def get_or_create_portfolio() -> Portfolio:
    p, _ = Portfolio.objects.get_or_create(
        name="paper",
        defaults={
            "cash": settings.STARTING_CASH,
            "starting_cash": settings.STARTING_CASH,
            "active_strategy": "sma_crossover",
        },
    )
    return p


@transaction.atomic
def buy(portfolio: Portfolio, symbol: str, dollars: float, price: float, note: str = "", strategy: str = "") -> Fill | None:
    if price <= 0 or dollars <= 0 or dollars > portfolio.cash + 1e-9:
        return None
    shares = dollars / price
    portfolio.cash -= dollars
    portfolio.save(update_fields=["cash", "updated_at"])
    pos, _ = Position.objects.get_or_create(portfolio=portfolio, symbol=symbol, defaults={"shares": 0.0})
    pos.shares += shares
    pos.save(update_fields=["shares"])
    Trade.objects.create(
        portfolio=portfolio,
        action=Trade.BUY,
        symbol=symbol,
        shares=shares,
        price=price,
        note=note,
        strategy=strategy,
    )
    return Fill("BUY", symbol, shares, price, note)


@transaction.atomic
def sell(portfolio: Portfolio, symbol: str, shares: float, price: float, note: str = "", strategy: str = "") -> Fill | None:
    try:
        pos = Position.objects.get(portfolio=portfolio, symbol=symbol)
    except Position.DoesNotExist:
        return None
    if price <= 0 or shares <= 0 or shares > pos.shares + 1e-9:
        return None
    shares = min(shares, pos.shares)
    portfolio.cash += shares * price
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
        note=note,
        strategy=strategy,
    )
    return Fill("SELL", symbol, shares, price, note)


def sell_all(portfolio: Portfolio, symbol: str, price: float, note: str = "", strategy: str = "") -> Fill | None:
    try:
        pos = Position.objects.get(portfolio=portfolio, symbol=symbol)
    except Position.DoesNotExist:
        return None
    return sell(portfolio, symbol, pos.shares, price, note, strategy)


def apply_signals(portfolio: Portfolio, closes_map: dict, strategy_key: str, i: int | None = None) -> list[Fill]:
    strategy = get_strategy(strategy_key)
    fills: list[Fill] = []

    # Sells first to free cash
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
            # buy_hold dumps remaining cash into first signal; others use fraction
            fraction = 1.0 if strategy_key == "buy_hold" else settings.BUY_FRACTION
            budget = portfolio.cash * fraction
            f = buy(portfolio, sym, budget, price, note=f"{strategy.name} buy", strategy=strategy_key)
            if f:
                fills.append(f)
            portfolio.refresh_from_db()
    return fills


def run_tick(portfolio: Portfolio, symbols: list[str] | None = None) -> tuple[list[Fill], dict[str, float]]:
    symbols = symbols or list(settings.DEFAULT_SYMBOLS)
    closes = fetch_closes(symbols, days=90)
    fills = apply_signals(portfolio, closes, portfolio.active_strategy)
    return fills, latest_prices(closes)


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


def run_backtest(
    strategy_key: str,
    symbols: list[str],
    days: int = 90,
    cash: float = None,
) -> BacktestOutcome:
    """In-memory replay — does not touch the live paper portfolio."""
    cash = settings.STARTING_CASH if cash is None else cash
    strategy = get_strategy(strategy_key)
    closes = fetch_closes(symbols, days=days)

    dates = None
    for series in closes.values():
        dates = series.index if dates is None else dates.intersection(series.index)
    if dates is None or len(dates) < max(strategy.warmup, 5):
        raise RuntimeError("Not enough overlapping history to backtest.")

    aligned = {sym: closes[sym].loc[dates] for sym in closes}
    sim_cash = cash
    positions: dict[str, float] = {}
    events: list[dict] = []

    def sim_buy(sym: str, dollars: float, price: float, day) -> None:
        nonlocal sim_cash
        if dollars <= 0 or dollars > sim_cash or price <= 0:
            return
        shares = dollars / price
        sim_cash -= dollars
        positions[sym] = positions.get(sym, 0.0) + shares
        events.append({"date": str(day.date()), "action": "BUY", "symbol": sym, "shares": shares, "price": price})

    def sim_sell_all(sym: str, price: float, day) -> None:
        nonlocal sim_cash
        held = positions.get(sym, 0.0)
        if held <= 0 or price <= 0:
            return
        sim_cash += held * price
        events.append({"date": str(day.date()), "action": "SELL", "symbol": sym, "shares": held, "price": price})
        positions.pop(sym, None)

    for i in range(len(dates)):
        day = dates[i]
        # sells
        for sym, series in aligned.items():
            if strategy.signal_at(series, i) == Signal.SELL and positions.get(sym, 0) > 0:
                sim_sell_all(sym, float(series.iloc[i]), day)
        # buys
        for sym, series in aligned.items():
            if strategy.signal_at(series, i) == Signal.BUY and sim_cash > 1:
                fraction = 1.0 if strategy_key == "buy_hold" else settings.BUY_FRACTION
                sim_buy(sym, sim_cash * fraction, float(series.iloc[i]), day)

    prices = {sym: float(s.iloc[-1]) for sym, s in aligned.items()}
    held_val = sum(shares * prices.get(sym, 0.0) for sym, shares in positions.items())
    ending = sim_cash + held_val
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
    )


def outcome_log(outcome: BacktestOutcome) -> str:
    return json.dumps(
        {
            "events": outcome.events[-50:],  # cap stored log
            "final_positions": outcome.final_positions,
            "final_cash": outcome.final_cash,
        }
    )
