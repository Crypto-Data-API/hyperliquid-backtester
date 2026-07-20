"""Strategy base class and the context object handed to it each bar.

Design note — lookahead safety
------------------------------
A strategy never receives the full price series. On bar *i* it receives a
:class:`Context` whose arrays are sliced ``[: i + 1]``, so indexing past the
present is impossible rather than merely discouraged. ``ctx.close[-1]`` is
always "now"; there is no ``ctx.close[i + 1]`` to read by accident.

Orders fill on the **next** bar's open (see ``Backtester``), which is the
other half of the guarantee: a signal computed from bar *i*'s close cannot be
filled at bar *i*'s close.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

Side = Literal["long", "short"]


@dataclass(frozen=True)
class Signal:
    """A request to open a position, returned from :meth:`Strategy.on_bar`."""

    side: Side
    reason: str = "signal"
    #: Optional hard stop / take-profit as a fraction of entry price (0.05 = 5%).
    stop_pct: float | None = None
    take_pct: float | None = None
    #: Free-form values carried onto the resulting trade — e.g. the baseline
    #: level you intend to revert to. Surfaces in the demo chart.
    meta: dict = field(default_factory=dict)


@dataclass
class Position:
    """An open position. Mutated by the engine as the bar loop advances."""

    side: Side
    entry_price: float
    entry_index: int
    entry_time: int
    size: float
    notional: float
    leverage: float
    stop_pct: float | None = None
    take_pct: float | None = None
    funding_paid: float = 0.0
    meta: dict = field(default_factory=dict)

    def unrealised_pct(self, price: float) -> float:
        """Return on *margin*, so leverage is included."""
        raw = (price - self.entry_price) / self.entry_price
        if self.side == "short":
            raw = -raw
        return raw * self.leverage

    def bars_held(self, index: int) -> int:
        return index - self.entry_index


@dataclass
class Context:
    """Everything a strategy may see on the current bar — and nothing more."""

    index: int
    time: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    #: Per-bar funding rate, forward-filled. Zeros when unavailable.
    funding_rate: np.ndarray
    symbol: str
    timeframe: str

    @property
    def price(self) -> float:
        """Current close."""
        return float(self.close[-1])

    @property
    def bar_time(self) -> int:
        return int(self.time[-1])

    def __len__(self) -> int:
        return int(self.close.size)


class Strategy:
    """Subclass this, set the class attributes, implement :meth:`on_bar`.

    ``strategies/examples/`` has two complete implementations.
    """

    #: Shown in reports and used as the default run label.
    name: str = "unnamed"
    #: Bars required before ``on_bar`` is called at all.
    warmup: int = 100
    #: Maximum simultaneous open positions for this strategy.
    max_positions: int = 1
    #: Fraction of equity committed per position, before leverage.
    position_size_pct: float = 0.5
    #: Leverage applied to the position notional.
    leverage: float = 1.0

    def __init__(self, **params):
        for key, value in params.items():
            if not hasattr(self, key):
                raise AttributeError(
                    f"{type(self).__name__} has no parameter {key!r}. "
                    f"Declare it as a class attribute to make it tunable."
                )
            setattr(self, key, value)

    # -- overrides ---------------------------------------------------------

    def on_bar(self, ctx: Context) -> Signal | None:
        """Return a :class:`Signal` to open a position, or ``None``."""
        raise NotImplementedError

    def should_exit(self, ctx: Context, position: Position) -> str | None:
        """Return a non-empty reason string to close ``position``, else ``None``.

        Called before :meth:`on_bar` on every bar while a position is open.
        Hard stop, take-profit and liquidation are handled by the engine and
        do not need repeating here.
        """
        return None

    # -- introspection -----------------------------------------------------

    def params(self) -> dict:
        """Every tunable class attribute and its current value."""
        skip = {"name", "warmup"}
        out = {}
        for klass in reversed(type(self).__mro__):
            for key, value in vars(klass).items():
                if key.startswith("_") or callable(value) or key in skip:
                    continue
                if isinstance(value, (int, float, str, bool)):
                    out[key] = getattr(self, key)
        return out

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name}>"
