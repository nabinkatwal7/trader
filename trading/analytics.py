"""Portfolio stats helpers."""

from __future__ import annotations


def max_drawdown_pct(equity_points: list[float]) -> float:
    if not equity_points:
        return 0.0
    peak = equity_points[0]
    worst = 0.0
    for v in equity_points:
        peak = max(peak, v)
        if peak > 0:
            dd = (v - peak) / peak
            worst = min(worst, dd)
    return worst * 100


def trade_stats(trades) -> dict:
    """trades: sequence of Trade."""
    items = list(trades)
    sells = [t for t in items if t.action == "SELL" and t.realized_pnl is not None]
    wins = [t for t in sells if t.realized_pnl > 0]
    losses = [t for t in sells if t.realized_pnl < 0]
    realized = sum(t.realized_pnl or 0 for t in sells)
    fees = sum(getattr(t, "fee", 0) or 0 for t in items)
    return {
        "trade_count": len(items),
        "sell_count": len(sells),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(sells) * 100) if sells else 0.0,
        "realized_pnl": realized,
        "fees_paid": fees,
        "avg_win": (sum(t.realized_pnl for t in wins) / len(wins)) if wins else 0.0,
        "avg_loss": (sum(t.realized_pnl for t in losses) / len(losses)) if losses else 0.0,
    }


def allocation_rows(positions, prices: dict[str, float], cash: float) -> list[dict]:
    rows = []
    total = cash + sum(p.shares * prices.get(p.symbol, 0.0) for p in positions)
    if total <= 0:
        return [{"label": "Cash", "value": cash, "pct": 100.0}]
    rows.append({"label": "Cash", "value": cash, "pct": cash / total * 100})
    for p in positions:
        val = p.shares * prices.get(p.symbol, 0.0)
        rows.append({"label": p.symbol, "value": val, "pct": val / total * 100})
    return rows
