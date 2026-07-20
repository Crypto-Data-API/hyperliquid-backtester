"""Moving-average crossover — the canonical trend-following baseline.

Included as the simplest complete strategy in the repo: roughly forty lines,
one entry rule, one exit rule. Use it to check your data synced correctly and
your environment works, and as a shape to copy when writing your own.

It is also a useful control. Mean-reversion and trend-following fail in
opposite regimes, so running both over the same window tells you more about
the window than either does alone.

It loses money here — deliberately left that way
------------------------------------------------
On the 71-day BTC 15m window in this repo it returns about -17%, and the
temptation is to tune until it doesn't. We tried, and the result is worth more
than a green number would have been.

**900 configurations** were searched over fast/slow lengths, stops, targets and
long-only. Ranked on the first 70% of the window, the best config returned
**+13.64%** with an expectancy of +$50 per trade. It looked like the strongest
strategy in the repo.

Run once on the remaining 30% that the search had never seen, that same config
returned **-3.43%**. **None of the top eight survived**, and all of them clustered
on the same fast=40/slow=120 island — one stretch of price, fitted.

That gap between +13.64% and -3.43% is the entire content of
``docs/VALIDATION.md``, produced by this engine on this data. Ship the tuned
version and it would have been the best-looking row on the dashboard and
completely fake. So the defaults here are untuned, and the strategy stays red.

Reference implementation, not a recommendation.
"""

from __future__ import annotations

import numpy as np

from hlbt.indicators import ema
from hlbt.strategy import Context, Position, Signal, Strategy


class SmaCross(Strategy):
    name = "sma_cross (example)"
    warmup = 60

    fast_length = 12
    slow_length = 48
    hard_stop_pct = 0.05
    hard_take_pct = 0.15
    allow_short = True

    position_size_pct = 0.5
    leverage = 1.0

    def _lines(self, close: np.ndarray) -> tuple[float, float, float, float]:
        fast = ema(close, self.fast_length)
        slow = ema(close, self.slow_length)
        return fast[-1], slow[-1], fast[-2], slow[-2]

    def on_bar(self, ctx: Context) -> Signal | None:
        if len(ctx) < self.slow_length + 2:
            return None
        f, s, pf, ps = self._lines(ctx.close)
        if not all(np.isfinite(x) for x in (f, s, pf, ps)):
            return None

        if pf <= ps and f > s:
            return Signal(
                side="long", reason="golden_cross",
                stop_pct=self.hard_stop_pct, take_pct=self.hard_take_pct,
                meta={"fast": float(f), "slow": float(s)},
            )
        if self.allow_short and pf >= ps and f < s:
            return Signal(
                side="short", reason="death_cross",
                stop_pct=self.hard_stop_pct, take_pct=self.hard_take_pct,
                meta={"fast": float(f), "slow": float(s)},
            )
        return None

    def should_exit(self, ctx: Context, position: Position) -> str | None:
        if len(ctx) < self.slow_length + 2:
            return None
        f, s, _, _ = self._lines(ctx.close)
        if not (np.isfinite(f) and np.isfinite(s)):
            return None
        if position.side == "long" and f < s:
            return "cross_against"
        if position.side == "short" and f > s:
            return "cross_against"
        return None


strategy = SmaCross
