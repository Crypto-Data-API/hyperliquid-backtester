# Writing a strategy

A strategy is one class with two methods. Put it anywhere; `strategies/user/`
is gitignored so yours stays private.

```python
from hlbt.indicators import atr, rsi, sma
from hlbt.strategy import Context, Position, Signal, Strategy


class MyStrategy(Strategy):
    name = "my_strategy"
    warmup = 100          # bars before on_bar is called at all

    length = 20           # any class attribute is tunable from the CLI
    threshold = 0.03

    position_size_pct = 0.5
    leverage = 1.0

    def on_bar(self, ctx: Context) -> Signal | None:
        """Return a Signal to open a position, or None."""
        mean = sma(ctx.close, self.length)[-1]
        if ctx.price < mean * (1 - self.threshold):
            return Signal(side="long", reason="below_mean",
                          stop_pct=0.05, take_pct=0.10)
        return None

    def should_exit(self, ctx: Context, position: Position) -> str | None:
        """Return a reason string to close, or None. Called before on_bar."""
        mean = sma(ctx.close, self.length)[-1]
        if position.side == "long" and ctx.price >= mean:
            return "reverted_to_mean"
        return None


strategy = MyStrategy      # the loader looks for this
```

Run it:

```bash
hlbt run --strategy strategies/user/my_strategy.py --symbol BTC --timeframe 15m
hlbt run --strategy strategies/user/my_strategy.py --symbol BTC \
  --set length=40 --set threshold=0.05
```

`--set` rejects unknown names rather than silently ignoring them, so a typo
fails loudly instead of quietly running the default.

## The context

`ctx` holds the market **up to and including the current bar** — arrays sliced
`[:i+1]`. There is no future to index into, so lookahead is impossible rather
than merely discouraged.

| Field | What it is |
|---|---|
| `ctx.close`, `ctx.open`, `ctx.high`, `ctx.low`, `ctx.volume` | numpy arrays, oldest first |
| `ctx.funding_rate` | per-bar funding, forward-filled |
| `ctx.time` | epoch ms per bar |
| `ctx.price` | current close — same as `ctx.close[-1]` |
| `ctx.index` | absolute bar number |
| `len(ctx)` | bars available so far |

`ctx.close[-1]` is now, `ctx.close[-2]` is the previous bar. Always guard
against `nan` — indicators return `nan` during warm-up:

```python
value = sma(ctx.close, self.length)[-1]
if not np.isfinite(value):
    return None
```

## Signals

```python
Signal(
    side="long",              # or "short"
    reason="breakout",        # appears on the trade record
    stop_pct=0.05,            # hard stop, fraction of entry price
    take_pct=0.10,            # take profit
    meta={"level": 63000.0},  # carried onto the trade, shown in the replay
)
```

Returning a `Signal` **queues** an order — it fills at the **next** bar's open,
never at the close that generated it.

Stop and take-profit are checked by the engine against each bar's high and low.
When one bar spans both, **the stop wins** — intrabar sequence is unknowable
from OHLC, so the ambiguity resolves pessimistically rather than flatteringly.

## Positions

In `should_exit`:

```python
position.side                     # "long" / "short"
position.entry_price
position.bars_held(ctx.index)
position.unrealised_pct(ctx.price)  # return on margin, includes leverage
position.funding_paid             # negative = you have paid funding
position.meta                     # whatever you attached to the Signal
```

A time stop is usually worth having — it scratches trades whose thesis simply
never materialised:

```python
def should_exit(self, ctx, position):
    if position.bars_held(ctx.index) >= 240:
        return "time_stop"
    ...
```

## Indicators

`hlbt.indicators` ships `sma`, `ema`, `wma`, `hma`, `alma`, `rsi`, `atr`,
`true_range`, `stddev`, `bollinger`. All vectorised, all returning `nan`
through the warm-up rather than a back-filled value that would look real.

Writing your own is just numpy — see `alma` for the shape. If you are building
a mean-reversion family, the baseline estimator is where most of the design
space lives: a laggy mean flags a stretch late and gets run over by trends, a
mean that hugs price never registers a stretch at all. Swapping `sma` for a
Hull, KAMA, VIDYA, FRAMA or Kalman baseline gives a materially different
strategy from the same entry logic. [AlgoBrain](https://github.com/Crypto-Data-API/algobrain)
documents that family in depth.

## Sizing and leverage

```python
position_size_pct = 0.5     # fraction of equity as margin
leverage = 3.0              # notional = margin * leverage
```

Leverage multiplies gains, losses, **and** funding, and it sets the liquidation
distance — at 5× a ~10% adverse move liquidates. The engine models liquidation
against each bar's adverse extreme, so leveraged strategies do get stopped out
the way they would live. Start at 1× and add leverage only once the unleveraged
version has an edge.

## Debugging

```bash
hlbt run --strategy ... --symbol BTC --json-out results/run.json
hlbt demo results/run.json
```

The replay is the fastest way to find a broken strategy. Entries in obviously
wrong places, positions held far too long, or a flat equity curve with no
markers all show up instantly on the chart and are nearly invisible in a
summary table.

No trades at all usually means one of: `warmup` longer than your data,
thresholds too tight, or an indicator returning `nan` — print
`np.isfinite(value)` inside `on_bar` to check.

Before trusting any result, read [VALIDATION.md](VALIDATION.md).
