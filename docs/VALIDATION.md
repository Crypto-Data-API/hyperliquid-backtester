# Before you believe a backtest

A profitable backtest is weak evidence. This page is about the ways a good
number turns out to be noise, and what this engine does and does not model.

## The multiple-comparisons problem

This is the big one, and it is not intuitive.

Test one strategy and a good result is mildly informative. Test a thousand
variants and keep the best, and you have built a machine for finding noise. The
best of a thousand random strategies will look excellent *by construction* —
that is what "best of a thousand" means.

The literature is blunt about it. Harvey and Liu, surveying the ~316 factors
published in the equity cross-section, propose a
[haircut Sharpe ratio](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2345489)
whose penalty grows non-linearly with the number of trials — at 50 trials a
marginal strategy loses nearly half its apparent Sharpe. Bailey and López de
Prado's [Deflated Sharpe Ratio](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)
adjusts significance for the number of trials, plus skew and kurtosis. Their
related work shows the
[probability of selecting an overfit strategy](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)
rises sharply with trial count.

Practical consequences:

- **Count your trials and write the number down.** Every parameter sweep, every
  tweak-and-rerun. If you cannot say how many variants you tried, you cannot
  interpret the winner.
- **Prefer few, economically-motivated hypotheses over many arbitrary ones.**
  "Forced liquidations overshoot and revert" is a reason. "Length 34 beat
  length 20" is not.
- **A parameter that only works at one exact value is noise.** Real edges
  degrade gracefully — plot performance across the range and look for a
  plateau, not a spike.

## Split your data before you look at it

Decide the split first, then look:

```bash
hlbt sync --symbol BTC --timeframe 15m --days 120
# develop on the first ~70%, then run once on the rest
```

The holdout is only worth something while it is untouched. Once you have tuned
against it, it is training data, and you need a new one. Nothing enforces this
for you.

## Read past the win rate

A high win rate is the most seductive and least informative number available.
A strategy taking small profits and occasional large losses can win 80% of its
trades and still lose money. `hlbt run` always prints these together:

| Metric | What it tells you |
|---|---|
| Win rate | Frequency only. Meaningless alone. |
| **Profit factor** | Gross wins / gross losses. Below 1 is a losing strategy regardless of win rate. |
| **Expectancy** | Average P&L per trade. The number that actually compounds. |
| **Max drawdown** | The loss you must survive. Decides whether the strategy is holdable. |
| **Fees** | Compare to net profit. If fees exceed profit, the edge belongs to the exchange. |
| Sharpe | Risk-adjusted return. Unstable on short windows and few trades. |

## Sample size

Twenty trades tells you almost nothing; a 70% win rate over 20 trades is
consistent with a coin flip. Prefer a few hundred. If a strategy only trades
rarely, extend the window rather than accepting the small sample — and treat
sub-50-trade results as a hypothesis, not a finding.

## What this engine does not model

Being explicit, because these all push results in the optimistic direction:

- **Order-book depth.** Fills assume your size is absorbed at one price. On thin
  alt-perp books it will not be, and the measured "signal" may be bid-ask bounce
  rather than a real move — you cross the very spread the backtest scored as
  profit. This is the single largest gap between these results and live trading.
- **Partial fills and queue position.** Every fill is complete and immediate.
- **Funding rate changes within a bar.** The rate is forward-filled per bar.
- **Exchange downtime, API failures, rejected orders.**
- **Market impact.** Your orders never move the price.
- **Liquidation mechanics in detail.** Approximated from leverage and a
  maintenance-margin fraction, not exchange-specific tiering or auto-deleveraging.

Slippage (`--slippage`, default 2bps) is a crude proxy for the first two. If
you are trading size or illiquid symbols, raise it substantially and see whether
the strategy survives. If a small increase in assumed costs destroys the result,
the result was never real.

## A sane sequence

1. Write the economic reason the edge should exist. If you cannot, stop.
2. Implement it plainly. Do not tune yet.
3. Run on your development window with realistic fees and funding.
4. Check trade count and the fees-to-profit ratio before anything else.
5. Vary parameters and look for a plateau, not a peak. **Count the variants.**
6. Run once on the holdout. Accept the result.
7. Replay it (`hlbt demo`) and watch the drawdowns. Ask whether you would have
   held through them at 3am.
8. Paper trade. Live fills will still disappoint you relative to this.

Nothing here is financial advice. See the disclaimer in the
[README](../README.md).
