"""Vectorised indicator primitives.

Every function takes and returns numpy arrays aligned to the input series.
Leading values that cannot be computed are ``np.nan`` rather than back-filled,
so a strategy can never accidentally read a warm-up value as a real signal.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "sma", "ema", "wma", "rsi", "atr", "true_range",
    "bollinger", "stddev", "hma", "alma",
]


def _as_float(x) -> np.ndarray:
    return np.asarray(x, dtype=float)


def sma(values, period: int) -> np.ndarray:
    """Simple moving average."""
    v = _as_float(values)
    out = np.full(v.shape, np.nan)
    if period <= 0 or v.size < period:
        return out
    csum = np.cumsum(np.insert(v, 0, 0.0))
    out[period - 1:] = (csum[period:] - csum[:-period]) / period
    return out


def ema(values, period: int) -> np.ndarray:
    """Exponential moving average, seeded with the first ``period`` SMA."""
    v = _as_float(values)
    out = np.full(v.shape, np.nan)
    if period <= 0 or v.size < period:
        return out
    alpha = 2.0 / (period + 1.0)
    out[period - 1] = v[:period].mean()
    for i in range(period, v.size):
        out[i] = v[i] * alpha + out[i - 1] * (1.0 - alpha)
    return out


def wma(values, period: int) -> np.ndarray:
    """Linearly weighted moving average."""
    v = _as_float(values)
    out = np.full(v.shape, np.nan)
    if period <= 0 or v.size < period:
        return out
    w = np.arange(1.0, period + 1.0)
    w /= w.sum()
    for i in range(period - 1, v.size):
        out[i] = float(np.dot(v[i - period + 1:i + 1], w))
    return out


def hma(values, period: int) -> np.ndarray:
    """Hull moving average — WMA(2*WMA(n/2) - WMA(n), sqrt(n))."""
    v = _as_float(values)
    if period <= 1 or v.size < period:
        return np.full(v.shape, np.nan)
    half, root = max(1, period // 2), max(1, int(np.sqrt(period)))
    raw = 2.0 * wma(v, half) - wma(v, period)
    return wma(np.nan_to_num(raw, nan=0.0), root)


def alma(values, period: int, offset: float = 0.85, sigma: float = 6.0) -> np.ndarray:
    """Arnaud Legoux moving average — Gaussian weights with an offset."""
    v = _as_float(values)
    out = np.full(v.shape, np.nan)
    if period <= 0 or v.size < period:
        return out
    m = offset * (period - 1)
    s = period / sigma
    idx = np.arange(period)
    w = np.exp(-((idx - m) ** 2) / (2.0 * s * s))
    w /= w.sum()
    for i in range(period - 1, v.size):
        out[i] = float(np.dot(v[i - period + 1:i + 1], w))
    return out


def stddev(values, period: int) -> np.ndarray:
    """Rolling population standard deviation."""
    v = _as_float(values)
    out = np.full(v.shape, np.nan)
    if period <= 0 or v.size < period:
        return out
    for i in range(period - 1, v.size):
        out[i] = float(v[i - period + 1:i + 1].std())
    return out


def bollinger(values, period: int = 20, mult: float = 2.0):
    """Bollinger bands. Returns ``(middle, upper, lower)``."""
    mid = sma(values, period)
    sd = stddev(values, period)
    return mid, mid + mult * sd, mid - mult * sd


def true_range(high, low, close) -> np.ndarray:
    """Wilder's true range. First element is ``high - low``."""
    h, l, c = _as_float(high), _as_float(low), _as_float(close)
    prev = np.roll(c, 1)
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    if tr.size:
        tr[0] = h[0] - l[0]
    return tr


def atr(high, low, close, period: int = 14) -> np.ndarray:
    """Average true range, Wilder-smoothed (RMA)."""
    tr = true_range(high, low, close)
    out = np.full(tr.shape, np.nan)
    if period <= 0 or tr.size < period:
        return out
    out[period - 1] = tr[:period].mean()
    for i in range(period, tr.size):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def rsi(values, period: int = 14) -> np.ndarray:
    """Wilder's RSI. ``period=2`` gives the Connors short-horizon variant."""
    v = _as_float(values)
    out = np.full(v.shape, np.nan)
    if period <= 0 or v.size <= period:
        return out
    delta = np.diff(v)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    ag, al = gain[:period].mean(), loss[:period].mean()

    def _rsi(g: float, l: float) -> float:
        if l == 0.0:
            return 100.0 if g > 0 else 50.0
        rs = g / l
        return 100.0 - (100.0 / (1.0 + rs))

    out[period] = _rsi(ag, al)
    for i in range(period + 1, v.size):
        ag = (ag * (period - 1) + gain[i - 1]) / period
        al = (al * (period - 1) + loss[i - 1]) / period
        out[i] = _rsi(ag, al)
    return out
