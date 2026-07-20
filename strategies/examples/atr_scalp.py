"""ATR scalp — fade a short, sharp extension and take a small fixed profit.

A scalper in the literal sense: hold for minutes to hours, not days. Price is
constantly overshooting its own short-term average by a bar or two of noise,
and on a liquid perp that overshoot reverts often enough to pay — provided you
take the small win and leave, rather than waiting for a *reason* to exit.

Three things make this different from ``bollinger_revert``, which shares the
"fade the extension" thesis:

* **The yardstick is ATR, not standard deviation.** ATR reacts to real range
  rather than to the dispersion of closes, so a single violent bar registers
  immediately instead of being averaged into a slow-moving band.
* **The exit is a fixed distance, not the mean.** Take ``target_atr`` and go.
  Waiting for price to touch a moving average means the target drifts away
  from you exactly when the trade is going wrong.
* **There is a hard clock.** ``max_bars`` closes the position whether or not it
  worked. A scalp that has not paid within a few bars is no longer the trade
  you entered — the overshoot has become a move.

Because targets are small, **costs dominate**. Every trade pays two fee legs
and crosses the spread twice, so a scalper with a real edge before costs can
still lose money after them. Check the fees line against net profit before
believing any result here, and raise ``--slippage`` to see how quickly the
edge dies — that is the honest test for anything trading this often.

Reference implementation. Not a recommendation.
"""

from __future__ import annotations

import numpy as np

from hlbt.indicators import atr, ema
from hlbt.strategy import Context, Position, Signal, Strategy


class AtrScalp(Strategy):
    name = "atr_scalp (example)"
    warmup = 80

    # -- entry -------------------------------------------------------------
    fast_length = 10        # the short-term average price is stretched from
    entry_atr = 1.4         # ATR multiples of stretch required to fade
    atr_period = 14
    min_atr_pct = 0.08      # volatility floor: below this the "stretch" is spread

    # -- exit --------------------------------------------------------------
    target_atr = 0.9        # fixed take-profit, in ATR
    stop_atr = 1.8          # fixed stop, in ATR
    max_bars = 10           # hard clock — a scalp that hasn't paid is stale

    allow_short = True
    cooldown_bars = 1

    # -- sizing ------------------------------------------------------------
    position_size_pct = 0.5
    leverage = 1.0

    def __init__(self, **params):
        super().__init__(**params)
        self._last_exit_index = -10_000

    def on_bar(self, ctx: Context) -> Signal | None:
        if ctx.index - self._last_exit_index < self.cooldown_bars:
            return None

        close = ctx.close
        mid = ema(close, self.fast_length)[-1]
        a = atr(ctx.high, ctx.low, close, self.atr_period)[-1]
        price = close[-1]
        if not (np.isfinite(mid) and np.isfinite(a)) or a <= 0:
            return None

        # a "stretch" in dead tape is usually just the spread moving
        if (a / price) * 100.0 < self.min_atr_pct:
            return None

        stretch = (price - mid) / a          # in ATR units, signed
        # express the fixed ATR distances as fractions of entry price
        take = (self.target_atr * a) / price
        stop = (self.stop_atr * a) / price

        if stretch <= -self.entry_atr:
            return Signal(
                side="long", reason="stretched_below",
                stop_pct=stop, take_pct=take,
                meta={"stretch_atr": round(float(stretch), 3)},
            )
        if self.allow_short and stretch >= self.entry_atr:
            return Signal(
                side="short", reason="stretched_above",
                stop_pct=stop, take_pct=take,
                meta={"stretch_atr": round(float(stretch), 3)},
            )
        return None

    def should_exit(self, ctx: Context, position: Position) -> str | None:
        # the engine handles the ATR stop and target; this is the clock
        if position.bars_held(ctx.index) >= self.max_bars:
            self._last_exit_index = ctx.index
            return "max_bars"
        return None


strategy = AtrScalp
