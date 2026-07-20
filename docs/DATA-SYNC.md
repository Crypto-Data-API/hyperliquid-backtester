# Populating and syncing market data

The engine reads local JSON under `data/`. `hlbt sync` fills it from the
[CryptoDataAPI backtesting archive](https://cryptodataapi.com/backtest-data).

```bash
hlbt sync --symbol BTC --timeframe 15m --days 90
hlbt sync --symbol BTC ETH SOL HYPE --timeframe 1h --days 180
hlbt sync --symbol BTCUSDT --timeframe 4h --days 365 --exchange binance
```

Files land at `data/<exchange>/<SYMBOL>-<timeframe>.json`.

## Getting a key

Free key, no card, at [cryptodataapi.com/login](https://cryptodataapi.com/login), or by email:

```bash
curl -X POST https://cryptodataapi.com/api/v1/auth/keys \
  -H "Content-Type: application/json" -d '{"email":"you@example.com"}'
```

Then:

```bash
export CRYPTODATA_API_KEY=cdk_live_yourkey          # Windows: $env:CRYPTODATA_API_KEY="..."
```

**Tiers.** The bulk history endpoints this tool calls — `/backtesting/klines` and
`/backtesting/funding` — require **Pro Plus**. The free tier (5 req/min, 50/day)
covers the live endpoints and the daily snapshots, but not bulk history. A 403
from sync almost always means the key is below Pro Plus.

New signups: **20% off with `SOCIAL20`, first 10 only.**

## How it works

1. Fetches **1-minute** klines for the window, paging until covered.
2. Fetches the funding series (rate, open interest, mark price).
3. Resamples the 1m bars to your timeframe, aligned to the epoch — a 15m bar
   always starts on :00, :15, :30 or :45.
4. Forward-fills the funding rate onto each bar. The archive samples funding
   every 5 minutes; a bar takes the most recent rate at or before its open.
5. **Drops an incomplete trailing bar.** A partial bar is the classic way a
   backtest reads a price that had not settled, so it is discarded rather than
   half-counted.

## Keeping it current

Sync is incremental. Re-running extends the cache from its last bar:

```bash
hlbt sync --symbol BTC --timeframe 15m --days 90    # extends, does not refetch
hlbt sync --symbol BTC --timeframe 15m --force      # full refetch
```

A daily cron is enough to stay current:

```cron
0 1 * * *  cd /path/to/hyperliquid-backtester && \
           CRYPTODATA_API_KEY=cdk_live_... .venv/bin/hlbt sync \
           --symbol BTC ETH SOL --timeframe 15m --days 120
```

## Coverage — read this before trusting a long backtest

Coverage differs by endpoint, and the difference matters.

**The query endpoints** (`/backtesting/klines`, `/backtesting/funding`) serve a
rolling recent window. At the time of writing, Hyperliquid BTC 1-minute klines
go back roughly **70 days**. Requesting an earlier `start` silently clamps to
the earliest available bar rather than erroring — so always check the date
range sync reports:

```
wrote 6882 bars (2026-05-09 -> 2026-07-19) to data/hyperliquid/BTC-15m.json
```

**The Parquet archive** (`/backtesting/archives/download`) goes considerably
deeper — pre-signed download URLs, no auth header needed on the URL itself:

| Data | Exchange | Depth |
|---|---|---|
| `klines` (1m) | hyperliquid | ~111 days rolling |
| `klines_deep` 1d | hyperliquid | to 2023 launch |
| `klines_deep` 4h | hyperliquid | ~29 months |
| `klines_deep` 1h | hyperliquid | ~8 months |
| `klines_deep` 1d/4h/1h | binance | to each market's listing — BTCUSDT to Aug 2017 |
| `funding_deep` (hourly) | hyperliquid | ~39 months |

Check what exists before planning a run:

```bash
curl -H "X-API-Key: $CRYPTODATA_API_KEY" \
  https://cryptodataapi.com/api/v1/backtesting/archives/index
```

Two caveats worth knowing: **deep 1-minute data does not exist** on either
source, so sub-hourly strategies are limited to the rolling window; and
`funding_deep` carries the rate and premium but **no historical open interest
or mark price** — those begin in the rolling 5-minute files.

## Using your own data

Nothing is locked to the sync tool. Write a JSON array to
`data/<exchange>/<SYMBOL>-<timeframe>.json`:

```json
[{"time": 1784246400000, "open": 63815.0, "high": 63822.0,
  "low": 63791.0, "close": 63822.0, "volume": 21.28,
  "funding_rate": 0.0000125}]
```

`time` is epoch milliseconds at the bar's **open**, ascending, no gaps.
`funding_rate` is per-bar and optional — omit it and funding costs are zero,
which will flatter any strategy that holds positions.
