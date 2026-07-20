"""Bar-by-bar event-driven backtest engine.

Order of operations on each bar — deliberate, and worth reading before you
trust a number this produces:

1. **Fill pending orders at this bar's open.** A signal raised on bar *i*
   fills at bar *i+1*'s open, never at bar *i*'s close.
2. **Accrue funding** on any open position.
3. **Check liquidation** against the bar's adverse extreme (low for longs,
   high for shorts).
4. **Check hard stop, then take-profit** — in that order, and both against the
   bar's extremes. When a single bar spans both, the **stop wins**. Intrabar
   sequence is unknowable from OHLC, so the engine resolves the ambiguity
   pessimistically rather than flattering the result.
5. **Ask the strategy to exit** (``should_exit``), evaluated at the close.
6. **Ask the strategy to enter** (``on_bar``), queued for the next bar.

Fees are charged on both legs at the taker rate by default. Funding is charged
per bar from the real per-bar rate when you sync it; if you backtest without
funding, a perpetual carry strategy will look better than it is.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict

import numpy as np

from .strategy import Context, Position, Signal, Strategy

log = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    initial_capital: float = 10_000.0
    #: Taker fee per leg, as a fraction. Hyperliquid taker is ~0.035%.
    taker_fee: float = 0.00035
    #: Slippage applied against you on entry and exit, as a fraction.
    slippage: float = 0.0002
    #: Fraction of margin remaining at which the position is liquidated.
    #: 0.5 means "liquidated once half the posted margin is gone".
    maintenance_margin_fraction: float = 0.5
    #: Charge funding to open positions. Turn off only to measure its impact.
    apply_funding: bool = True


@dataclass
class Trade:
    symbol: str
    side: str
    entry_time: int
    exit_time: int
    entry_index: int
    exit_index: int
    entry_price: float
    exit_price: float
    size: float
    notional: float
    leverage: float
    margin: float
    gross_pnl: float
    fees: float
    funding_pnl: float
    net_pnl: float
    return_pct: float
    bars_held: int
    exit_reason: str
    meta: dict = field(default_factory=dict)


@dataclass
class BacktestResult:
    strategy: str
    symbol: str
    timeframe: str
    trades: list[Trade]
    equity_curve: list[dict]
    config: dict
    params: dict

    def summary(self) -> dict:
        """Headline metrics. Returns zeros rather than raising on no trades."""
        from . import metrics
        return metrics.summarise(self)

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "summary": self.summary(),
            "params": self.params,
            "config": self.config,
            "trades": [asdict(t) for t in self.trades],
            "equity_curve": self.equity_curve,
        }


class Backtester:
    """Run one strategy against one symbol's bars."""

    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()

    def run(
        self,
        strategy: Strategy,
        bars: dict[str, np.ndarray],
        symbol: str,
        timeframe: str,
    ) -> BacktestResult:
        cfg = self.config
        t = np.asarray(bars["time"], dtype=np.int64)
        o = np.asarray(bars["open"], dtype=float)
        h = np.asarray(bars["high"], dtype=float)
        l = np.asarray(bars["low"], dtype=float)
        c = np.asarray(bars["close"], dtype=float)
        v = np.asarray(bars.get("volume", np.zeros_like(c)), dtype=float)
        fr = np.asarray(
            bars.get("funding_rate", np.zeros_like(c)), dtype=float
        )
        fr = np.nan_to_num(fr, nan=0.0)

        n = c.size
        if n <= strategy.warmup:
            raise ValueError(
                f"{n} bars is not enough for {strategy.name} "
                f"(warmup={strategy.warmup}). Sync a longer window."
            )

        equity = cfg.initial_capital
        position: Position | None = None
        pending: Signal | None = None
        trades: list[Trade] = []
        curve: list[dict] = []
        peak = equity

        for i in range(n):
            price = float(c[i])

            # 1. fill anything queued on the previous bar, at this bar's open
            if pending is not None and position is None:
                position = self._open(pending, float(o[i]), i, int(t[i]), equity, strategy)
                equity -= self._entry_fee(position)
            pending = None

            if position is not None:
                # 2. funding
                if cfg.apply_funding and fr[i]:
                    sign = 1.0 if position.side == "long" else -1.0
                    paid = -sign * float(fr[i]) * position.notional
                    position.funding_paid += paid
                    equity += paid

                # 3. liquidation, against the adverse extreme
                adverse = float(l[i]) if position.side == "long" else float(h[i])
                if position.unrealised_pct(adverse) <= -cfg.maintenance_margin_fraction:
                    liq = self._liquidation_price(position)
                    equity = self._close(
                        position, liq, i, int(t[i]), equity, trades, symbol, "liquidation"
                    )
                    position = None

            if position is not None:
                exit_price, reason = self._stop_or_take(position, float(h[i]), float(l[i]))
                if reason:
                    equity = self._close(
                        position, exit_price, i, int(t[i]), equity, trades, symbol, reason
                    )
                    position = None

            ctx = Context(
                index=i, time=t[: i + 1], open=o[: i + 1], high=h[: i + 1],
                low=l[: i + 1], close=c[: i + 1], volume=v[: i + 1],
                funding_rate=fr[: i + 1], symbol=symbol, timeframe=timeframe,
            )

            if position is not None:
                reason = strategy.should_exit(ctx, position)
                if reason:
                    equity = self._close(
                        position, price, i, int(t[i]), equity, trades, symbol, reason
                    )
                    position = None

            if position is None and i >= strategy.warmup and i < n - 1:
                signal = strategy.on_bar(ctx)
                if signal is not None:
                    pending = signal

            mark = equity
            if position is not None:
                mark = equity + position.unrealised_pct(price) * self._margin(position)
            peak = max(peak, mark)
            curve.append({
                "time": int(t[i]),
                "equity": round(mark, 6),
                "drawdown": round((mark - peak) / peak * 100.0 if peak else 0.0, 6),
            })

        # close anything still open on the final bar, so equity is realised
        if position is not None:
            equity = self._close(
                position, float(c[-1]), n - 1, int(t[-1]), equity, trades, symbol,
                "end_of_data",
            )

        return BacktestResult(
            strategy=strategy.name, symbol=symbol, timeframe=timeframe,
            trades=trades, equity_curve=curve,
            config=asdict(cfg), params=strategy.params(),
        )

    # -- internals ---------------------------------------------------------

    def _margin(self, p: Position) -> float:
        return p.notional / p.leverage

    def _entry_fee(self, p: Position) -> float:
        return p.notional * self.config.taker_fee

    def _open(
        self, signal: Signal, raw_price: float, index: int, time: int,
        equity: float, strategy: Strategy,
    ) -> Position:
        slip = self.config.slippage
        price = raw_price * (1.0 + slip) if signal.side == "long" else raw_price * (1.0 - slip)
        margin = equity * strategy.position_size_pct
        notional = margin * strategy.leverage
        return Position(
            side=signal.side, entry_price=price, entry_index=index, entry_time=time,
            size=notional / price if price else 0.0, notional=notional,
            leverage=strategy.leverage, stop_pct=signal.stop_pct,
            take_pct=signal.take_pct, meta=dict(signal.meta),
        )

    def _liquidation_price(self, p: Position) -> float:
        """Price at which margin is exhausted to the maintenance fraction."""
        move = self.config.maintenance_margin_fraction / p.leverage
        return p.entry_price * (1.0 - move) if p.side == "long" else p.entry_price * (1.0 + move)

    def _stop_or_take(
        self, p: Position, high: float, low: float
    ) -> tuple[float, str | None]:
        """Stop is checked first — a bar touching both resolves as a loss."""
        if p.stop_pct:
            stop = (p.entry_price * (1.0 - p.stop_pct) if p.side == "long"
                    else p.entry_price * (1.0 + p.stop_pct))
            if (p.side == "long" and low <= stop) or (p.side == "short" and high >= stop):
                return stop, "stop_loss"
        if p.take_pct:
            take = (p.entry_price * (1.0 + p.take_pct) if p.side == "long"
                    else p.entry_price * (1.0 - p.take_pct))
            if (p.side == "long" and high >= take) or (p.side == "short" and low <= take):
                return take, "take_profit"
        return 0.0, None

    def _close(
        self, p: Position, raw_price: float, index: int, time: int, equity: float,
        trades: list[Trade], symbol: str, reason: str,
    ) -> float:
        slip = self.config.slippage
        price = raw_price * (1.0 - slip) if p.side == "long" else raw_price * (1.0 + slip)
        move = (price - p.entry_price) / p.entry_price
        if p.side == "short":
            move = -move
        gross = move * p.notional
        exit_fee = p.notional * self.config.taker_fee
        fees = self._entry_fee(p) + exit_fee
        net = gross - exit_fee + p.funding_paid
        margin = self._margin(p)

        equity += net
        trades.append(Trade(
            symbol=symbol, side=p.side, entry_time=p.entry_time, exit_time=time,
            entry_index=p.entry_index, exit_index=index,
            entry_price=round(p.entry_price, 8), exit_price=round(price, 8),
            size=round(p.size, 8), notional=round(p.notional, 6),
            leverage=p.leverage, margin=round(margin, 6),
            gross_pnl=round(gross, 6), fees=round(fees, 6),
            funding_pnl=round(p.funding_paid, 6), net_pnl=round(net, 6),
            return_pct=round(net / margin * 100.0 if margin else 0.0, 6),
            bars_held=index - p.entry_index, exit_reason=reason, meta=p.meta,
        ))
        return equity
