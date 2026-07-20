"""Populate and refresh local market data from CryptoDataAPI.

The archive stores Hyperliquid and Binance klines at 1-minute resolution plus
a separate funding series. This module pulls both, resamples to whatever
timeframe you asked for, joins funding onto the bars, and caches the result as
JSON under ``data/``.

Sync is **incremental**: an existing cache file is extended from its last bar
rather than refetched, so keeping a symbol current is cheap.

    hlbt sync --symbol BTC --timeframe 15m --days 111

Get a free key at https://cryptodataapi.com/login (no card), or:

    curl -X POST https://cryptodataapi.com/api/v1/auth/keys \\
      -H "Content-Type: application/json" -d '{"email":"you@example.com"}'

Note the tiers: ``/backtesting/klines`` and ``/backtesting/funding`` require
**Pro Plus**. The free tier covers live endpoints and the daily snapshots, but
not the bulk history this module fetches.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

API_BASE = os.environ.get("CRYPTODATA_API_BASE", "https://cryptodataapi.com/api/v1")
DATA_DIR = Path(os.environ.get("HLBT_DATA_DIR", "data"))

TIMEFRAME_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
    "30m": 1_800_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
}


class SyncError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.environ.get("CRYPTODATA_API_KEY", "").strip()
    if not key:
        raise SyncError(
            "CRYPTODATA_API_KEY is not set.\n"
            "  Get a free key: https://cryptodataapi.com/login\n"
            "  Then: export CRYPTODATA_API_KEY=cdk_live_...\n"
            "  (bulk history needs a Pro Plus key)"
        )
    return key


def _get(client: httpx.Client, path: str, params: dict) -> dict:
    url = f"{API_BASE}{path}"
    for attempt in range(5):
        r = client.get(url, params=params, headers={"X-API-Key": _api_key()}, timeout=60.0)
        if r.status_code == 429:
            wait = min(2 ** attempt, 30)
            log.warning("rate limited, retrying in %ss", wait)
            time.sleep(wait)
            continue
        if r.status_code == 403:
            raise SyncError(
                f"403 from {path}. Bulk history requires a Pro Plus key — "
                "see https://cryptodataapi.com/pricing"
            )
        if r.status_code == 401:
            raise SyncError("401 — CRYPTODATA_API_KEY is invalid or revoked.")
        r.raise_for_status()
        return r.json()
    raise SyncError(f"giving up on {path} after repeated rate limiting")


def fetch_klines(
    symbol: str, start: str, end: str, exchange: str = "hyperliquid",
) -> list[dict]:
    """Fetch raw 1-minute klines, paging until the window is covered."""
    out: list[dict] = []
    cursor = start
    with httpx.Client() as client:
        while True:
            payload = _get(client, "/backtesting/klines", {
                "symbol": symbol, "exchange": exchange,
                "start": cursor, "end": end, "limit": 10_000,
            })
            batch = payload.get("klines", [])
            if not batch:
                break
            raw_len = len(batch)          # page-size test uses the RAW length;
            last_t = batch[-1]["t"]       # de-duping first ends paging early
            if out:
                batch = [b for b in batch if b["t"] > out[-1]["t"]]
            if not batch and raw_len < 10_000:
                break
            out.extend(batch)
            last = datetime.fromtimestamp(last_t / 1000, tz=timezone.utc)
            log.info("  %s klines -> %s", len(out), last.date())
            if raw_len < 10_000:
                break
            nxt = (last + timedelta(minutes=1)).strftime("%Y-%m-%d")
            if nxt == cursor:             # window did not advance — bail rather
                break                     # than loop forever on a clamped start
            cursor = nxt
            if cursor > end:
                break
    return out


def fetch_funding(
    symbol: str, start: str, end: str, exchange: str = "hyperliquid",
) -> list[dict]:
    """Fetch the funding series (rate, open interest, mark price)."""
    out: list[dict] = []
    cursor = start
    with httpx.Client() as client:
        while True:
            payload = _get(client, "/backtesting/funding", {
                "symbol": symbol, "exchange": exchange,
                "start": cursor, "end": end, "limit": 10_000,
            })
            batch = payload.get("data", [])
            if not batch:
                break
            raw_len = len(batch)
            last_t = batch[-1]["time"]
            if out:
                batch = [b for b in batch if b["time"] > out[-1]["time"]]
            if not batch and raw_len < 10_000:
                break
            out.extend(batch)
            if raw_len < 10_000:
                break
            last = datetime.fromtimestamp(last_t / 1000, tz=timezone.utc)
            nxt = (last + timedelta(minutes=1)).strftime("%Y-%m-%d")
            if nxt == cursor:
                break
            cursor = nxt
            if cursor > end:
                break
    return out


def resample(klines: list[dict], timeframe: str) -> list[dict]:
    """Aggregate 1-minute klines into ``timeframe`` buckets.

    Buckets are aligned to the epoch, so a 15m bar always starts on :00, :15,
    :30 or :45. The final bucket is dropped unless it is complete — a partial
    bar is the classic way a backtest reads a price that had not settled yet.
    """
    step = TIMEFRAME_MS.get(timeframe)
    if step is None:
        raise SyncError(f"unsupported timeframe {timeframe!r}")
    if step == 60_000:
        return [
            {"time": k["t"], "open": k["o"], "high": k["h"],
             "low": k["l"], "close": k["c"], "volume": k["v"] or 0.0}
            for k in klines
        ]

    buckets: dict[int, dict] = {}
    for k in klines:
        b = (k["t"] // step) * step
        cur = buckets.get(b)
        if cur is None:
            buckets[b] = {
                "time": b, "open": k["o"], "high": k["h"],
                "low": k["l"], "close": k["c"], "volume": k["v"] or 0.0,
                "_bars": 1,
            }
        else:
            cur["high"] = max(cur["high"], k["h"])
            cur["low"] = min(cur["low"], k["l"])
            cur["close"] = k["c"]
            cur["volume"] += k["v"] or 0.0
            cur["_bars"] += 1

    expected = step // 60_000
    ordered = [buckets[b] for b in sorted(buckets)]
    if ordered and ordered[-1]["_bars"] < expected:
        log.info("dropping incomplete final bar (%s/%s minutes)",
                 ordered[-1]["_bars"], expected)
        ordered.pop()
    for bar in ordered:
        bar.pop("_bars", None)
    return ordered


def attach_funding(bars: list[dict], funding: list[dict], timeframe: str) -> list[dict]:
    """Forward-fill the funding rate onto each bar.

    The archive samples funding every 5 minutes; a bar takes the most recent
    rate at or before its open. Bars before the first funding sample get 0.0.
    """
    if not funding:
        for bar in bars:
            bar["funding_rate"] = 0.0
        return bars

    series = sorted(((f["time"], f.get("funding_rate") or 0.0) for f in funding))
    times = [s[0] for s in series]
    rates = [s[1] for s in series]

    import bisect
    for bar in bars:
        idx = bisect.bisect_right(times, bar["time"]) - 1
        bar["funding_rate"] = rates[idx] if idx >= 0 else 0.0
    return bars


def cache_path(symbol: str, timeframe: str, exchange: str) -> Path:
    return DATA_DIR / exchange / f"{symbol}-{timeframe}.json"


def sync(
    symbol: str, timeframe: str = "15m", days: int = 90,
    exchange: str = "hyperliquid", force: bool = False,
) -> Path:
    """Sync one symbol. Extends an existing cache unless ``force``."""
    path = cache_path(symbol, timeframe, exchange)
    path.parent.mkdir(parents=True, exist_ok=True)

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)

    existing: list[dict] = []
    if path.exists() and not force:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing:
            last = datetime.fromtimestamp(
                existing[-1]["time"] / 1000, tz=timezone.utc
            ).date()
            if last >= end:
                log.info("%s %s already current (%s bars, through %s)",
                         symbol, timeframe, len(existing), last)
                return path
            start = last
            log.info("extending %s %s from %s", symbol, timeframe, start)

    s, e = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    log.info("syncing %s %s %s -> %s", exchange, symbol, s, e)

    klines = fetch_klines(symbol, s, e, exchange)
    if not klines:
        raise SyncError(
            f"no klines for {symbol} on {exchange} in {s}..{e}. "
            "Check coverage: /api/v1/backtesting/archives/index"
        )
    funding = fetch_funding(symbol, s, e, exchange)
    bars = attach_funding(resample(klines, timeframe), funding, timeframe)

    if existing:
        cutoff = existing[-1]["time"]
        bars = existing + [b for b in bars if b["time"] > cutoff]

    path.write_text(json.dumps(bars), encoding="utf-8")
    first = datetime.fromtimestamp(bars[0]["time"] / 1000, tz=timezone.utc).date()
    last = datetime.fromtimestamp(bars[-1]["time"] / 1000, tz=timezone.utc).date()
    log.info("wrote %s bars (%s -> %s) to %s", len(bars), first, last, path)
    return path


def load(symbol: str, timeframe: str = "15m", exchange: str = "hyperliquid") -> dict:
    """Load a synced cache into the column arrays the engine expects."""
    import numpy as np
    path = cache_path(symbol, timeframe, exchange)
    if not path.exists():
        raise SyncError(
            f"no local data at {path}\n"
            f"  Run: hlbt sync --symbol {symbol} --timeframe {timeframe}"
        )
    bars = json.loads(path.read_text(encoding="utf-8"))
    return {
        "time": np.array([b["time"] for b in bars], dtype=np.int64),
        "open": np.array([b["open"] for b in bars], dtype=float),
        "high": np.array([b["high"] for b in bars], dtype=float),
        "low": np.array([b["low"] for b in bars], dtype=float),
        "close": np.array([b["close"] for b in bars], dtype=float),
        "volume": np.array([b.get("volume", 0.0) for b in bars], dtype=float),
        "funding_rate": np.array(
            [b.get("funding_rate", 0.0) for b in bars], dtype=float
        ),
    }
