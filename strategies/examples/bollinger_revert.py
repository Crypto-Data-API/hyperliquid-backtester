"""Bollinger reversion — fade a band pierce, exit back at the mean.

The whole family of mean-reversion strategies shares one idea: measure how far
price has stretched from an adaptive mean, and fade the extension. Here the
mean is a simple moving average and the stretch threshold is a multiple of
rolling standard deviation, which is the textbook starting point.

What you change to build a different strategy is the *baseline estimator*.
A laggy mean flags a stretch late and gets run over by trends; a mean that
hugs price too tightly never registers a stretch at all. Choosing that
estimator is most of the design space — ALMA, Hull, KAMA, VIDYA, FRAMA,
Kalman, Theil-Sen and others all trade lag against noise-robustness
differently. Swap ``_baseline`` and you have a new strategy.

Reference implementation. Tune and validate your own parameters — and read
``docs/VALIDATION.md`` first — before risking capital.
"""

from __future__ import annotations

import numpy as np

from hlbt.indicators import atr, rsi, sma, stddev
from hlbt.strategy import Context, Position, Signal, Strategy


class BollingerRevert(Strategy):
    name = "bollinger_revert (example)"
    warmup = 100

    # -- entry -------------------------------------------------------------
    length = 20             # baseline lookback
    band_mult = 2.5         # stddev multiples to call a stretch
    rsi_period = 2          # Connors-style short RSI
    rsi_overbought = 92.0
    rsi_oversold = 8.0
    min_atr_pct = 0.15      # skip dead tape: ATR as % of price
    require_close_inside = True   # close must still be on the fade's side

    # -- exit --------------------------------------------------------------
    hard_stop_pct = 0.06    # the binding stop
    hard_take_pct = 0.12    # guard, rarely hit — the mean exit fires first
    time_stop_bars = 240    # scratch if it never reverts
    cooldown_bars = 2

    # -- sizing ------------------------------------------------------------
    position_size_pct = 0.5
    leverage = 1.0

    def __init__(self, **params):
        super().__init__(**params)
        self._last_exit_index = -10_000

    def _baseline(self, close: np.ndarray) -> np.ndarray:
        """Swap this for ALMA/Hull/KAMA/VIDYA to make a new strategy."""
        return sma(close, self.length)

    def on_bar(self, ctx: Context) -> Signal | None:
        if ctx.index - self._last_exit_index < self.cooldown_bars:
            return None

        close, high, low = ctx.close, ctx.high, ctx.low
        base = self._baseline(close)
        sd = stddev(close, self.length)
        a = atr(high, low, close, 14)
        r = rsi(close, self.rsi_period)

        mid, dev = base[-1], sd[-1]
        atr_now, rsi_now, price = a[-1], r[-1], close[-1]
        if not all(np.isfinite(x) for x in (mid, dev, atr_now, rsi_now)) or dev <= 0:
            return None

        # volatility floor — a "stretch" in flat tape is usually spread noise
        if (atr_now / price) * 100.0 < self.min_atr_pct:
            return None

        upper = mid + self.band_mult * dev
        lower = mid - self.band_mult * dev

        # short: the bar's high pierced the upper band, RSI is hyper-extended,
        # and the close is still above the mean (the fade hasn't happened yet)
        if high[-1] >= upper and rsi_now >= self.rsi_overbought:
            if not self.require_close_inside or price > mid:
                return Signal(
                    side="short", reason="upper_band_stretch",
                    stop_pct=self.hard_stop_pct, take_pct=self.hard_take_pct,
                    meta={"baseline": float(mid), "band": float(upper)},
                )

        if low[-1] <= lower and rsi_now <= self.rsi_oversold:
            if not self.require_close_inside or price < mid:
                return Signal(
                    side="long", reason="lower_band_stretch",
                    stop_pct=self.hard_stop_pct, take_pct=self.hard_take_pct,
                    meta={"baseline": float(mid), "band": float(lower)},
                )
        return None

    def should_exit(self, ctx: Context, position: Position) -> str | None:
        held = position.bars_held(ctx.index)

        if held >= self.time_stop_bars:
            self._last_exit_index = ctx.index
            return "time_stop"

        base = self._baseline(ctx.close)
        mid = base[-1]
        if not np.isfinite(mid):
            return None

        # the real exit: price has reverted to the mean
        price = ctx.price
        reverted = (
            (position.side == "short" and price <= mid)
            or (position.side == "long" and price >= mid)
        )
        if reverted and held > 0:
            self._last_exit_index = ctx.index
            return "reverted_to_mean"
        return None


strategy = BollingerRevert
