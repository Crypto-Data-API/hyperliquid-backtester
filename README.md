# Hyperliquid Backtester

> Sync real Hyperliquid market data, test a strategy against it with honest costs, then **watch the backtest replay bar by bar**.

A small, readable backtesting engine for crypto perpetuals. No framework to learn, no config pyramid — one strategy class, one CLI, one self-contained HTML chart you can scrub through.

```bash
pip install -e .
export CRYPTODATA_API_KEY=cdk_live_yourkey

hlbt sync --symbol BTC --timeframe 15m --days 90
hlbt run  --strategy strategies/examples/bollinger_revert.py --symbol BTC --json-out results/btc.json
hlbt demo results/btc.json          # → results/btc.html, press Play
```

Then open `results/index.html` — every run you have exported, sorted by return,
each one a click away from its replay.

---

## Why this exists

Most backtests lie in the same three ways, so this engine is opinionated about all three:

**Fees and slippage are charged by default.** Both legs, taker rate, plus slippage against you on entry *and* exit. In the example run below, fees came to **$605 against $172 of net profit** — the strategy is only marginally profitable, and a zero-fee backtest would have shown it as a clear winner. That is the single most common way a backtest flatters a strategy that loses money live.

**Funding is charged by default.** Perpetuals pay or receive funding every hour. Any strategy holding more than a bar or two is materially affected, and a backtest that ignores it is not modelling a perp.

**Lookahead is structurally impossible.** A strategy never receives the full price series — on bar *i* it gets arrays sliced `[:i+1]`, so there is no future bar to index into by accident. Orders fill at the **next** bar's open, never at the close that generated the signal.

---

## The replay

`hlbt demo` writes one self-contained HTML file: candles, entry and exit markers, an equity curve, and a play button that walks the backtest forward in time.

A summary table tells you a strategy made 1.7% with a 67% win rate. The replay tells you it spent five weeks underwater first. Those are very different things to know before you risk money, and only one of them is visible in a table.

Controls: **Space** play/pause · **←/→** step one bar · scrub bar · 1× to 64× · jump to end.

The chart fills the window, and the logo goes back to the run index. `hlbt demo`
refreshes that index automatically; `hlbt index results` rebuilds it on demand.

---

## Getting the data

The engine reads local JSON, and `hlbt sync` populates it from the
[CryptoDataAPI](https://cryptodataapi.com/backtest-data) backtesting archive —
Hyperliquid and Binance klines plus the matching funding series.

```bash
hlbt sync --symbol BTC ETH SOL --timeframe 15m --days 90
hlbt sync --symbol BTC --timeframe 1h --days 365 --exchange binance
```

Sync is incremental — re-running extends the cache from its last bar rather than refetching, so a daily cron keeps everything current cheaply. 1-minute bars are resampled locally to your timeframe, and an incomplete trailing bar is dropped rather than half-counted.

**Getting a key.** Free key, no card, at [cryptodataapi.com/login](https://cryptodataapi.com/login) — or:

```bash
curl -X POST https://cryptodataapi.com/api/v1/auth/keys \
  -H "Content-Type: application/json" -d '{"email":"you@example.com"}'
```

Bulk history (`/backtesting/klines`, `/backtesting/funding`) needs a **Pro Plus** key; the free tier covers the live endpoints and daily snapshots. Full detail and coverage windows: [docs/DATA-SYNC.md](docs/DATA-SYNC.md).

**New signups get 20% off with code `SOCIAL20` — first 10 only.**

---

## Writing a strategy

```python
from hlbt.indicators import atr, rsi, sma
from hlbt.strategy import Context, Position, Signal, Strategy

class MyStrategy(Strategy):
    name = "my_strategy"
    warmup = 100
    length = 20

    def on_bar(self, ctx: Context) -> Signal | None:
        mean = sma(ctx.close, self.length)[-1]
        if ctx.price < mean * 0.97:
            return Signal(side="long", stop_pct=0.05, take_pct=0.10)
        return None

    def should_exit(self, ctx: Context, position: Position) -> str | None:
        mean = sma(ctx.close, self.length)[-1]
        return "reverted" if ctx.price >= mean else None

strategy = MyStrategy
```

Tune without editing the file:

```bash
hlbt run --strategy strategies/user/my_strategy.py --symbol BTC \
  --set length=40 --set stop_pct=0.03
```

Full guide: [docs/WRITING-STRATEGIES.md](docs/WRITING-STRATEGIES.md).

### Your strategies stay yours

Anything in **`strategies/user/` is gitignored**. Strategies you write — or that an AI agent writes for you — never land in a commit or a public fork unless you explicitly `git add -f` them.

```
strategies/examples/    tracked — reference implementations
strategies/user/        gitignored — yours
```

---

## Included examples

| Strategy | Idea |
|---|---|
| `bollinger_revert.py` | Fade a band pierce, exit back at the mean. Swap one method to change the baseline estimator — that choice is most of the design space in mean reversion. |
| `sma_cross.py` | EMA crossover. The simplest complete strategy here, and a useful control. |

Run both over the same window and the contrast is the point:

```
bollinger_revert  BTC 15m        sma_cross  BTC 15m
  Trades          173              Trades          172
  Win rate        67.05%           Win rate        22.09%
  Profit factor   1.2055           Profit factor   0.65
  Total return    1.7168%          Total return    -17.5683%
  Max drawdown    -4.889%          Max drawdown    -20.097%
  Fees paid       605.38           Fees paid       542.85
```

Same symbol, same 71 days, opposite outcomes. Mean reversion and trend following fail in opposite regimes, so running both tells you more about the window than either does alone. Neither result is a prediction — swap the window and they can invert.

---

## Reading the numbers honestly

A **67% win rate** with a **profit factor of 1.21** means the losers are nearly as big as the winners. Win rate alone is close to meaningless — a strategy can win 80% of its trades and still lose money, and one of the strategies that inspired this repo does exactly that. `hlbt run` always prints profit factor, expectancy, max drawdown and fees alongside win rate for that reason.

Before you believe any backtest, read [docs/VALIDATION.md](docs/VALIDATION.md) — it covers the multiple-comparisons problem, why testing many variants makes a good-looking result *more* likely to be noise, and what this engine still does not model (order-book depth, partial fills, exchange downtime).

---

## Where the ideas come from

This repo is the *engine*. If you want a library of strategy ideas to implement in it, [**AlgoBrain**](https://github.com/Crypto-Data-API/algobrain) is a free knowledge base of crypto trading strategy — ~4,900 interlinked pages covering funding-rate harvesting, basis and carry, liquidation plays, market-making and mean-reversion families, plus the methodology for validating them. It ships a local MCP server, so an AI agent can read it directly and write strategies straight into `strategies/user/`.

Live market data for the agent itself:

```bash
claude mcp add --transport http cryptodataapi https://cryptodataapi.com/mcp
```

Keyless — a browser sign-in opens on the first tool call.

---

## Install

```bash
git clone https://github.com/Crypto-Data-API/hyperliquid-backtester.git
cd hyperliquid-backtester
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
```

Python 3.10+. Two dependencies: `numpy` and `httpx`.

---

## Disclaimer

This is research and educational software. **Nothing here is financial, investment, legal, or tax advice.** Backtest results are historical simulations, not predictions, and a profitable backtest is weak evidence a strategy will be profitable live.

Trading crypto derivatives carries a **substantial risk of loss**, and leverage amplifies it. The example strategies are reference implementations, not recommendations, and their parameters are illustrative rather than tuned. Do your own research and consult a licensed professional. You use this entirely at your own risk; the authors accept no liability for any loss arising from its use.

MIT licensed — see [LICENSE](LICENSE).
