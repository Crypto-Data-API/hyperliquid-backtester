"""Engine invariants — the properties a backtest must hold to be trustworthy."""

from __future__ import annotations

import numpy as np
import pytest

from hlbt.backtester import Backtester, BacktestConfig
from hlbt.indicators import atr, ema, rsi, sma
from hlbt.strategy import Context, Position, Signal, Strategy


def make_bars(n=500, seed=7, start=100.0):
    rng = np.random.default_rng(seed)
    steps = rng.normal(0, 0.5, n)
    close = start + np.cumsum(steps)
    high = close + np.abs(rng.normal(0, 0.2, n))
    low = close - np.abs(rng.normal(0, 0.2, n))
    open_ = np.concatenate([[start], close[:-1]])
    return {
        "time": np.arange(n, dtype=np.int64) * 900_000 + 1_700_000_000_000,
        "open": open_, "high": np.maximum(high, np.maximum(open_, close)),
        "low": np.minimum(low, np.minimum(open_, close)), "close": close,
        "volume": np.full(n, 10.0), "funding_rate": np.zeros(n),
    }


class AlwaysLong(Strategy):
    name = "always_long"
    warmup = 10

    def on_bar(self, ctx):
        return Signal(side="long")

    def should_exit(self, ctx, position):
        return "held_5" if position.bars_held(ctx.index) >= 5 else None


class Never(Strategy):
    name = "never"
    warmup = 10

    def on_bar(self, ctx):
        return None


# -- lookahead ------------------------------------------------------------

def test_context_never_exposes_the_future():
    """The whole safety story: ctx must end at the current bar."""
    bars = make_bars(200)
    seen = []

    class Spy(Strategy):
        name = "spy"
        warmup = 10

        def on_bar(self, ctx):
            seen.append((ctx.index, len(ctx), float(ctx.close[-1])))
            return None

    Backtester().run(Spy(), bars, "TEST", "15m")
    for index, length, last_close in seen:
        assert length == index + 1
        assert last_close == pytest.approx(bars["close"][index])


def test_entry_fills_on_the_next_bar_open():
    bars = make_bars(120)
    result = Backtester(BacktestConfig(slippage=0.0, taker_fee=0.0)).run(
        AlwaysLong(), bars, "TEST", "15m"
    )
    assert result.trades
    first = result.trades[0]
    # signal raised on the warmup bar; fill is the *next* bar's open
    assert first.entry_price == pytest.approx(bars["open"][first.entry_index])
    assert first.entry_index >= AlwaysLong.warmup


# -- costs ----------------------------------------------------------------

def test_fees_are_charged_on_both_legs():
    bars = make_bars(200)
    cfg = BacktestConfig(taker_fee=0.001, slippage=0.0)
    result = Backtester(cfg).run(AlwaysLong(), bars, "TEST", "15m")
    for trade in result.trades:
        assert trade.fees == pytest.approx(trade.notional * 0.002, rel=1e-6)


def test_zero_fee_run_beats_the_costed_run():
    bars = make_bars(400)
    costed = Backtester(BacktestConfig(taker_fee=0.001, slippage=0.001)).run(
        AlwaysLong(), bars, "TEST", "15m"
    )
    free = Backtester(BacktestConfig(taker_fee=0.0, slippage=0.0)).run(
        AlwaysLong(), bars, "TEST", "15m"
    )
    assert free.summary()["final_equity"] > costed.summary()["final_equity"]


def test_funding_is_charged_to_longs_when_positive():
    bars = make_bars(200)
    bars["funding_rate"] = np.full(len(bars["close"]), 0.0001)
    result = Backtester(BacktestConfig(taker_fee=0.0, slippage=0.0)).run(
        AlwaysLong(), bars, "TEST", "15m"
    )
    assert result.trades
    assert all(t.funding_pnl < 0 for t in result.trades)


def test_funding_can_be_disabled():
    bars = make_bars(200)
    bars["funding_rate"] = np.full(len(bars["close"]), 0.0001)
    result = Backtester(BacktestConfig(apply_funding=False)).run(
        AlwaysLong(), bars, "TEST", "15m"
    )
    assert all(t.funding_pnl == 0 for t in result.trades)


# -- exits ----------------------------------------------------------------

def test_stop_wins_when_one_bar_spans_stop_and_target():
    """Intrabar order is unknowable, so the pessimistic branch must win."""
    n = 60
    bars = make_bars(n, start=100.0)
    bars["close"] = np.full(n, 100.0)
    bars["open"] = np.full(n, 100.0)
    bars["high"] = np.full(n, 100.0)
    bars["low"] = np.full(n, 100.0)
    # one wide bar that touches both a -5% stop and a +10% target
    bars["high"][30] = 111.0
    bars["low"][30] = 94.0

    class Once(Strategy):
        name = "once"
        warmup = 10

        def __init__(self, **kw):
            super().__init__(**kw)
            self.fired = False

        def on_bar(self, ctx):
            if self.fired or ctx.index != 28:
                return None
            self.fired = True
            return Signal(side="long", stop_pct=0.05, take_pct=0.10)

    result = Backtester(BacktestConfig(slippage=0.0, taker_fee=0.0)).run(
        Once(), bars, "TEST", "15m"
    )
    assert [t.exit_reason for t in result.trades] == ["stop_loss"]


def test_open_position_is_closed_at_end_of_data():
    class Sticky(AlwaysLong):
        name = "sticky"

        def should_exit(self, ctx, position):
            return None

    result = Backtester().run(Sticky(), make_bars(120), "TEST", "15m")
    assert result.trades[-1].exit_reason == "end_of_data"


def test_leverage_triggers_liquidation():
    n = 200
    bars = make_bars(n)
    bars["close"] = np.linspace(100.0, 50.0, n)      # steady 50% decline
    bars["open"] = bars["close"].copy()
    bars["high"] = bars["close"] + 0.1
    bars["low"] = bars["close"] - 0.1

    class Levered(AlwaysLong):
        name = "levered"
        leverage = 10.0

        def should_exit(self, ctx, position):
            return None

    result = Backtester().run(Levered(), bars, "TEST", "15m")
    assert any(t.exit_reason == "liquidation" for t in result.trades)


# -- reporting ------------------------------------------------------------

def test_no_trades_is_reported_not_raised():
    result = Backtester().run(Never(), make_bars(120), "TEST", "15m")
    s = result.summary()
    assert s["total_trades"] == 0
    assert s["win_rate"] == 0.0
    assert "note" in s


def test_equity_curve_has_one_point_per_bar():
    bars = make_bars(300)
    result = Backtester().run(AlwaysLong(), bars, "TEST", "15m")
    assert len(result.equity_curve) == len(bars["close"])


def test_insufficient_data_raises_clearly():
    with pytest.raises(ValueError, match="warmup"):
        Backtester().run(AlwaysLong(), make_bars(5), "TEST", "15m")


def test_unknown_parameter_is_rejected():
    with pytest.raises(AttributeError, match="no parameter"):
        AlwaysLong(nonexistent_param=1)


# -- indicators -----------------------------------------------------------

def test_indicators_are_nan_through_warmup_not_backfilled():
    x = np.arange(1, 101, dtype=float)
    for series in (sma(x, 20), ema(x, 20), rsi(x, 14), atr(x, x - 1, x, 14)):
        assert np.isnan(series[0])
        assert np.isfinite(series[-1])


def test_sma_matches_a_hand_computed_window():
    x = np.array([1.0, 2, 3, 4, 5, 6])
    assert sma(x, 3)[-1] == pytest.approx(5.0)
    assert sma(x, 3)[2] == pytest.approx(2.0)


def test_rsi_saturates_on_a_monotonic_series():
    assert rsi(np.arange(1, 60, dtype=float), 14)[-1] == pytest.approx(100.0)
