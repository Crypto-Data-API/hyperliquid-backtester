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

The naive version's weakness is structural, not a matter of tuning: RSI can sit
pinned below 30 for the entire duration of a trend while price keeps falling.
"Oversold" is not the same as "about to bounce", and nothing in this strategy
knows the difference.

Reference implementation. Not a recommendation.
"""

from __future__ import annotations

import numpy as np

from hlbt.indicators import rsi
from hlbt.strategy import Context, Position, Signal, Strategy


class RsiReversion(Strategy):
    name = "rsi_reversion (example)"
    warmup = 60

    rsi_period = 14
    oversold = 30.0
    overbought = 70.0
    exit_level = 50.0        # reversion target: RSI back to the middle

    hard_stop_pct = 0.05
    hard_take_pct = 0.10
    time_stop_bars = 192     # two days on 15m — cut a thesis that never played out
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
