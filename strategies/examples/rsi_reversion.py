"""RSI reversion — the textbook mean-reversion strategy, deliberately naive.

Buy when RSI says oversold, sell when it says overbought, exit when it returns
to the middle. This is the first mean-reversion strategy almost everyone
writes, and it is here as a *control* rather than a recommendation.

Compare it with ``bollinger_revert``, which is the same underlying thesis with
three guards bolted on: a volatility floor so it ignores dead tape, a
distance-from-the-mean requirement so a shallow wobble is not treated as a
dislocation, and a much shorter RSI so only genuine extremes qualify. Running
both over the same window shows you what those guards are worth — which is a
more useful thing to learn than either result on its own.

The structural weakness survives any tuning: RSI can sit pinned below 30 for the
entire duration of a trend while price keeps falling. "Oversold" is not the same
as "about to bounce", and nothing in this strategy knows the difference.

How these parameters were chosen — read this before trusting the numbers
----------------------------------------------------------------------
They are **tuned**, and the honest accounting is:

* ~640 configurations were tried, ranked on the first 70% of a 71-day BTC 15m
  window (4,817 bars).
* The top candidates were then run once on the remaining 30% (2,065 bars) that
  the search had never seen. Four stayed positive; this is one of them.
* Out-of-sample that config produced **20 trades and +0.07%**. Positive, but on
  20 trades that is a coin flip's distance from zero. Treat it as "not obviously
  broken", not as evidence of an edge.

Over the full window it returns ~+2.1% with a 62% win rate. That number benefits
from hindsight — the window was chosen after the fact, and 640 trials is enough
that the best of them looks good whether or not anything real is there. See
``docs/VALIDATION.md``, and compare with ``sma_cross``, where the same procedure
turned +13.6% in-sample into -3.4% out of sample.

Reference implementation. Not a recommendation.
"""

from __future__ import annotations

import numpy as np

from hlbt.indicators import rsi
from hlbt.strategy import Context, Position, Signal, Strategy


class RsiReversion(Strategy):
    name = "rsi_reversion (example)"
    warmup = 60

    # These defaults are TUNED, not textbook — see the note at the bottom of
    # this docstring block. The classic settings are period 14 with 30/70.
    rsi_period = 9
    oversold = 15.0
    overbought = 75.0
    exit_level = 50.0        # reversion target: RSI back to the middle

    hard_stop_pct = 0.06
    hard_take_pct = 0.10
    time_stop_bars = 144     # 36h on 15m — cut a thesis that never played out
    allow_short = True

    position_size_pct = 0.5
    leverage = 1.0

    def on_bar(self, ctx: Context) -> Signal | None:
        r = rsi(ctx.close, self.rsi_period)
        value = r[-1]
        if not np.isfinite(value):
            return None

        if value <= self.oversold:
            return Signal(
                side="long", reason="rsi_oversold",
                stop_pct=self.hard_stop_pct, take_pct=self.hard_take_pct,
                meta={"rsi": float(value)},
            )
        if self.allow_short and value >= self.overbought:
            return Signal(
                side="short", reason="rsi_overbought",
                stop_pct=self.hard_stop_pct, take_pct=self.hard_take_pct,
                meta={"rsi": float(value)},
            )
        return None

    def should_exit(self, ctx: Context, position: Position) -> str | None:
        if position.bars_held(ctx.index) >= self.time_stop_bars:
            return "time_stop"

        value = rsi(ctx.close, self.rsi_period)[-1]
        if not np.isfinite(value):
            return None

        # exit once the oscillator has reverted to neutral
        if position.side == "long" and value >= self.exit_level:
            return "rsi_reverted"
        if position.side == "short" and value <= self.exit_level:
            return "rsi_reverted"
        return None


strategy = RsiReversion
