"""Performance metrics.

Deliberately includes the unflattering ones. A win rate on its own is close to
meaningless — a strategy can win 80% of its trades and still lose money — so
``summarise`` always reports profit factor, expectancy and max drawdown
alongside it.
"""

from __future__ import annotations

import math

BARS_PER_YEAR = {
    "1m": 525_600, "3m": 175_200, "5m": 105_120, "15m": 35_040,
    "30m": 17_520, "1h": 8_760, "4h": 2_190, "1d": 365,
}


def summarise(result) -> dict:
    trades = result.trades
    curve = result.equity_curve
    initial = result.config.get("initial_capital", 0.0)
    final = curve[-1]["equity"] if curve else initial

    if not trades:
        return {
            "total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "expectancy": 0.0, "total_return_pct": 0.0, "sharpe": 0.0,
            "max_drawdown_pct": 0.0, "final_equity": round(final, 2),
            "total_fees": 0.0, "total_funding": 0.0, "liquidations": 0,
            "note": "No trades. Check warmup, entry thresholds, and data window.",
        }

    pnls = [t.net_pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))

    returns = []
    for prev, cur in zip(curve, curve[1:]):
        if prev["equity"]:
            returns.append((cur["equity"] - prev["equity"]) / prev["equity"])
    sharpe = 0.0
    if len(returns) > 1:
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        sd = math.sqrt(var)
        if sd > 0:
            periods = BARS_PER_YEAR.get(result.timeframe, 35_040)
            sharpe = (mean / sd) * math.sqrt(periods)

    max_dd = min((p["drawdown"] for p in curve), default=0.0)

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100.0, 2),
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss else float("inf"),
        "expectancy": round(sum(pnls) / len(pnls), 4),
        "avg_win": round(gross_win / len(wins), 4) if wins else 0.0,
        "avg_loss": round(-gross_loss / len(losses), 4) if losses else 0.0,
        "total_return_pct": round((final - initial) / initial * 100.0, 4) if initial else 0.0,
        "sharpe": round(sharpe, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "final_equity": round(final, 2),
        "total_fees": round(sum(t.fees for t in trades), 4),
        "total_funding": round(sum(t.funding_pnl for t in trades), 4),
        "liquidations": sum(1 for t in trades if t.exit_reason == "liquidation"),
        "longs": sum(1 for t in trades if t.side == "long"),
        "shorts": sum(1 for t in trades if t.side == "short"),
    }
