"""
Paper trading bot — simulated money, real prices, simple strategy.

How it works (the 30-second version):
  1. You start with fake cash (default $1000).
  2. The bot looks at recent prices and computes two averages:
       short MA (fast) and long MA (slow).
  3. Buy signal:  short MA crosses ABOVE long MA  → momentum up.
     Sell signal: short MA crosses BELOW long MA  → momentum down.
  4. Buys spend cash for shares; sells turn shares back into cash.
  5. Portfolio value = cash + (shares × current price).

This is for learning. Fees/slippage are ignored. Not financial advice.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STARTING_CASH = 1000.0
PORTFOLIO_PATH = Path("portfolio.json")
# Default watchlist — liquid US stocks that teach clean price charts
DEFAULT_SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
SHORT_WINDOW = 5   # days
LONG_WINDOW = 20   # days
# Spend this fraction of cash on each buy signal (spread across opportunities)
BUY_FRACTION = 0.25

# ---------------------------------------------------------------------------
# Portfolio (cash + shares)
# ---------------------------------------------------------------------------


@dataclass
class Trade:
    time: str
    action: str  # BUY | SELL
    symbol: str
    shares: float
    price: float
    note: str = ""


@dataclass
class Portfolio:
    cash: float = STARTING_CASH
    positions: dict[str, float] = field(default_factory=dict)  # symbol → shares
    trades: list[dict] = field(default_factory=list)

    def value(self, prices: dict[str, float]) -> float:
        held = sum(shares * prices.get(sym, 0.0) for sym, shares in self.positions.items())
        return self.cash + held

    def buy(self, symbol: str, dollars: float, price: float, note: str = "") -> Trade | None:
        if price <= 0 or dollars <= 0 or dollars > self.cash:
            return None
        shares = dollars / price
        self.cash -= dollars
        self.positions[symbol] = self.positions.get(symbol, 0.0) + shares
        trade = Trade(_now(), "BUY", symbol, shares, price, note)
        self.trades.append(trade.__dict__)
        return trade

    def sell(self, symbol: str, shares: float, price: float, note: str = "") -> Trade | None:
        held = self.positions.get(symbol, 0.0)
        if price <= 0 or shares <= 0 or shares > held + 1e-12:
            return None
        shares = min(shares, held)
        self.cash += shares * price
        left = held - shares
        if left < 1e-12:
            self.positions.pop(symbol, None)
        else:
            self.positions[symbol] = left
        trade = Trade(_now(), "SELL", symbol, shares, price, note)
        self.trades.append(trade.__dict__)
        return trade

    def sell_all(self, symbol: str, price: float, note: str = "") -> Trade | None:
        return self.sell(symbol, self.positions.get(symbol, 0.0), price, note)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def load_portfolio(path: Path = PORTFOLIO_PATH) -> Portfolio:
    if not path.exists():
        return Portfolio()
    data = json.loads(path.read_text())
    return Portfolio(cash=data["cash"], positions=data.get("positions", {}), trades=data.get("trades", []))


def save_portfolio(p: Portfolio, path: Path = PORTFOLIO_PATH) -> None:
    path.write_text(json.dumps({"cash": p.cash, "positions": p.positions, "trades": p.trades}, indent=2))


# ---------------------------------------------------------------------------
# Market data + strategy
# ---------------------------------------------------------------------------


def fetch_history(symbols: list[str], days: int = 90):
    """Return {symbol: DataFrame with Close} using yfinance. Needs network."""
    import yfinance as yf

    # Auto-adjust handles splits/dividends so Close is usable as-is
    data = yf.download(
        symbols,
        period=f"{max(days, LONG_WINDOW + 5)}d",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    if data.empty:
        raise RuntimeError("No price data returned — check network / symbols.")

    # yfinance returns MultiIndex columns when multiple tickers
    closes = {}
    if len(symbols) == 1:
        closes[symbols[0]] = data["Close"].dropna()
    else:
        for sym in symbols:
            if sym in data["Close"].columns:
                closes[sym] = data["Close"][sym].dropna()
    return closes


def moving_averages(closes, short: int = SHORT_WINDOW, long: int = LONG_WINDOW):
    """Return (short_ma, long_ma) series aligned to closes."""
    return closes.rolling(short).mean(), closes.rolling(long).mean()


def signal_at(closes, i: int, short: int = SHORT_WINDOW, long: int = LONG_WINDOW) -> str:
    """
    Compare yesterday vs today crossover.
    Returns 'BUY', 'SELL', or 'HOLD'.
    """
    if i < long:
        return "HOLD"
    short_ma, long_ma = moving_averages(closes, short, long)
    # Need prior bar to detect a cross
    prev_short, prev_long = short_ma.iloc[i - 1], long_ma.iloc[i - 1]
    cur_short, cur_long = short_ma.iloc[i], long_ma.iloc[i]
    if any(x != x for x in (prev_short, prev_long, cur_short, cur_long)):  # NaN check
        return "HOLD"
    if prev_short <= prev_long and cur_short > cur_long:
        return "BUY"
    if prev_short >= prev_long and cur_short < cur_long:
        return "SELL"
    return "HOLD"


def latest_prices(closes_map: dict) -> dict[str, float]:
    return {sym: float(series.iloc[-1]) for sym, series in closes_map.items() if len(series)}


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def cmd_status(portfolio: Portfolio, symbols: list[str]) -> None:
    try:
        closes = fetch_history(symbols, days=LONG_WINDOW + 5)
        prices = latest_prices(closes)
    except Exception as e:
        print(f"(couldn't fetch live prices: {e})")
        prices = {}

    total = portfolio.value(prices) if prices else portfolio.cash
    print(f"Cash:      ${portfolio.cash:,.2f}")
    print(f"Positions:")
    if not portfolio.positions:
        print("  (none)")
    else:
        for sym, shares in portfolio.positions.items():
            px = prices.get(sym)
            if px is not None:
                print(f"  {sym:6}  {shares:10.4f} shares @ ${px:,.2f}  = ${shares * px:,.2f}")
            else:
                print(f"  {sym:6}  {shares:10.4f} shares")
    if prices:
        print(f"Total:     ${total:,.2f}   (P&L ${total - STARTING_CASH:+,.2f})")
    print(f"Trades:    {len(portfolio.trades)}")
    for t in portfolio.trades[-5:]:
        print(f"  {t['time']}  {t['action']:4} {t['shares']:.4f} {t['symbol']} @ ${t['price']:.2f}  {t.get('note','')}")


def cmd_reset(path: Path = PORTFOLIO_PATH) -> None:
    save_portfolio(Portfolio())
    print(f"Reset to ${STARTING_CASH:,.2f} cash. Saved → {path}")


def cmd_buy(portfolio: Portfolio, symbol: str, dollars: float) -> None:
    closes = fetch_history([symbol.upper()], days=5)
    price = latest_prices(closes)[symbol.upper()]
    trade = portfolio.buy(symbol.upper(), dollars, price, note="manual")
    if not trade:
        print(f"Can't buy ${dollars:.2f} of {symbol} (cash ${portfolio.cash:.2f}, price ${price:.2f})")
        return
    save_portfolio(portfolio)
    print(f"BUY  {trade.shares:.4f} {trade.symbol} @ ${trade.price:.2f}  (spent ${dollars:.2f})")


def cmd_sell(portfolio: Portfolio, symbol: str, shares: float | None) -> None:
    symbol = symbol.upper()
    closes = fetch_history([symbol], days=5)
    price = latest_prices(closes)[symbol]
    held = portfolio.positions.get(symbol, 0.0)
    qty = held if shares is None else shares
    trade = portfolio.sell(symbol, qty, price, note="manual")
    if not trade:
        print(f"Can't sell {qty} {symbol} (held {held:.4f})")
        return
    save_portfolio(portfolio)
    print(f"SELL {trade.shares:.4f} {trade.symbol} @ ${trade.price:.2f}  (got ${trade.shares * trade.price:.2f})")


def apply_signals(portfolio: Portfolio, closes_map: dict, i: int | None = None) -> list[Trade]:
    """Run strategy for one bar index (default: latest) across all symbols."""
    done: list[Trade] = []
    # Sells first (free cash), then buys
    for sym, series in closes_map.items():
        idx = len(series) - 1 if i is None else i
        if idx >= len(series):
            continue
        sig = signal_at(series, idx)
        price = float(series.iloc[idx])
        if sig == "SELL" and portfolio.positions.get(sym, 0) > 0:
            t = portfolio.sell_all(sym, price, note="MA crossover sell")
            if t:
                done.append(t)
    for sym, series in closes_map.items():
        idx = len(series) - 1 if i is None else i
        if idx >= len(series):
            continue
        sig = signal_at(series, idx)
        price = float(series.iloc[idx])
        if sig == "BUY" and portfolio.cash > 1:
            budget = portfolio.cash * BUY_FRACTION
            t = portfolio.buy(sym, budget, price, note="MA crossover buy")
            if t:
                done.append(t)
    return done


def cmd_tick(portfolio: Portfolio, symbols: list[str]) -> None:
    closes = fetch_history(symbols)
    trades = apply_signals(portfolio, closes)
    prices = latest_prices(closes)
    save_portfolio(portfolio)
    if not trades:
        print("No signals today — holding.")
    for t in trades:
        print(f"{t.action:4} {t.shares:.4f} {t.symbol} @ ${t.price:.2f}  ({t.note})")
    print(f"Portfolio value: ${portfolio.value(prices):,.2f}")


def cmd_backtest(symbols: list[str], days: int, cash: float) -> None:
    """Replay the strategy over recent history — best way to see how trading works."""
    closes = fetch_history(symbols, days=days)
    # Align on common dates
    dates = None
    for series in closes.values():
        dates = series.index if dates is None else dates.intersection(series.index)
    if dates is None or len(dates) < LONG_WINDOW + 2:
        print("Not enough history to backtest.")
        return

    paper = Portfolio(cash=cash)
    # Reindex each series to common dates
    aligned = {sym: closes[sym].loc[dates] for sym in closes}

    print(f"Backtest {days}d | start ${cash:,.2f} | MA {SHORT_WINDOW}/{LONG_WINDOW} | {', '.join(symbols)}")
    print("-" * 60)
    for i in range(LONG_WINDOW, len(dates)):
        day = dates[i]
        trades = apply_signals(paper, aligned, i)
        for t in trades:
            print(f"{day.date()}  {t.action:4} {t.shares:8.4f} {t.symbol:6} @ ${t.price:8.2f}")

    last_prices = {sym: float(s.iloc[-1]) for sym, s in aligned.items()}
    final = paper.value(last_prices)
    print("-" * 60)
    print(f"End cash: ${paper.cash:,.2f}")
    for sym, shares in paper.positions.items():
        print(f"  hold {shares:.4f} {sym} @ ${last_prices[sym]:.2f} = ${shares * last_prices[sym]:,.2f}")
    print(f"Final value: ${final:,.2f}   P&L ${final - cash:+,.2f} ({(final / cash - 1) * 100:+.1f}%)")
    print(f"Trades: {len(paper.trades)}")
    # Does NOT save — backtest is a sandbox replay


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Paper trading bot (simulated money, real prices).",
        epilog="Try:  python bot.py backtest   then   python bot.py status",
    )
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS), help="Comma-separated tickers")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Show cash, positions, recent trades")
    sub.add_parser("reset", help=f"Reset portfolio to ${STARTING_CASH:.0f}")
    sub.add_parser("tick", help="Fetch prices once and trade on MA signals")

    bt = sub.add_parser("backtest", help="Replay strategy over recent days (no save)")
    bt.add_argument("--days", type=int, default=90)
    bt.add_argument("--cash", type=float, default=STARTING_CASH)

    b = sub.add_parser("buy", help="Manually buy $ worth of a stock")
    b.add_argument("symbol")
    b.add_argument("dollars", type=float)

    s = sub.add_parser("sell", help="Manually sell shares (omit shares = sell all)")
    s.add_argument("symbol")
    s.add_argument("shares", type=float, nargs="?", default=None)

    args = p.parse_args(argv)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    portfolio = load_portfolio()

    if args.cmd == "status":
        cmd_status(portfolio, symbols)
    elif args.cmd == "reset":
        cmd_reset()
    elif args.cmd == "tick":
        cmd_tick(portfolio, symbols)
    elif args.cmd == "backtest":
        cmd_backtest(symbols, args.days, args.cash)
    elif args.cmd == "buy":
        cmd_buy(portfolio, args.symbol, args.dollars)
    elif args.cmd == "sell":
        cmd_sell(portfolio, args.symbol, args.shares)
    return 0


if __name__ == "__main__":
    sys.exit(main())
