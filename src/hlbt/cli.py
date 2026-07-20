"""``hlbt`` command line: sync data, run a backtest, export the demo chart."""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

from . import sync as sync_mod
from .backtester import Backtester, BacktestConfig
from .strategy import Strategy


def _load_strategy(path: str) -> type[Strategy]:
    """Import a strategy module by file path and find its class."""
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"strategy not found: {p}")
    spec = importlib.util.spec_from_file_location(p.stem, p)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import {p}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[p.stem] = module
    spec.loader.exec_module(module)

    if hasattr(module, "strategy"):
        return getattr(module, "strategy")
    for value in vars(module).values():
        if (isinstance(value, type) and issubclass(value, Strategy)
                and value is not Strategy):
            return value
    raise SystemExit(
        f"{p} defines no Strategy subclass. Export one as `strategy = MyClass`."
    )


def _parse_params(pairs: list[str]) -> dict:
    out: dict = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--set expects key=value, got {pair!r}")
        key, raw = pair.split("=", 1)
        try:
            out[key] = json.loads(raw)
        except json.JSONDecodeError:
            out[key] = raw
    return out


def cmd_sync(args) -> int:
    for symbol in args.symbol:
        sync_mod.sync(
            symbol=symbol, timeframe=args.timeframe, days=args.days,
            exchange=args.exchange, force=args.force,
        )
    return 0


def cmd_run(args) -> int:
    klass = _load_strategy(args.strategy)
    strategy = klass(**_parse_params(args.set or []))
    bars = sync_mod.load(args.symbol, args.timeframe, args.exchange)

    engine = Backtester(BacktestConfig(
        initial_capital=args.capital,
        taker_fee=args.fee,
        slippage=args.slippage,
        apply_funding=not args.no_funding,
    ))
    result = engine.run(strategy, bars, args.symbol, args.timeframe)
    payload = result.to_dict()

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {out}")

    s = payload["summary"]
    if args.quiet:
        print(json.dumps(s))
        return 0

    print()
    print(f"  {result.strategy}  {result.symbol} {result.timeframe}")
    print(f"  {'-' * 46}")
    for label, key, suffix in [
        ("Trades", "total_trades", ""),
        ("Win rate", "win_rate", "%"),
        ("Profit factor", "profit_factor", ""),
        ("Expectancy", "expectancy", " per trade"),
        ("Total return", "total_return_pct", "%"),
        ("Sharpe", "sharpe", ""),
        ("Max drawdown", "max_drawdown_pct", "%"),
        ("Final equity", "final_equity", ""),
        ("Fees paid", "total_fees", ""),
        ("Funding", "total_funding", ""),
        ("Liquidations", "liquidations", ""),
    ]:
        if key in s:
            print(f"  {label:<16}{s[key]}{suffix}")
    if s.get("note"):
        print(f"\n  {s['note']}")
    print()
    return 0


def cmd_demo(args) -> int:
    """Write the self-contained replay chart next to a result JSON."""
    from .demo import build_index, export
    out = export(Path(args.result), Path(args.out) if args.out else None)
    index = build_index(out.parent)          # keep the run list current
    print(f"wrote {out}\n  open it in a browser and press Play")
    print(f"wrote {index}")
    return 0


def cmd_index(args) -> int:
    """Rebuild the run index for a results directory."""
    from .demo import build_index
    directory = Path(args.dir)
    if not directory.is_dir():
        raise SystemExit(f"not a directory: {directory}")
    out = build_index(directory)
    print(f"wrote {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hlbt",
        description="Hyperliquid backtester — sync real market data, test a strategy, replay it.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sync", help="download and cache market data")
    p.add_argument("--symbol", nargs="+", required=True, help="e.g. BTC ETH SOL")
    p.add_argument("--timeframe", default="15m")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--exchange", default="hyperliquid", choices=["hyperliquid", "binance"])
    p.add_argument("--force", action="store_true", help="refetch instead of extending")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("run", help="run a strategy over synced data")
    p.add_argument("--strategy", required=True, help="path to a strategy .py")
    p.add_argument("--symbol", required=True)
    p.add_argument("--timeframe", default="15m")
    p.add_argument("--exchange", default="hyperliquid")
    p.add_argument("--capital", type=float, default=10_000.0)
    p.add_argument("--fee", type=float, default=0.00035, help="taker fee per leg")
    p.add_argument("--slippage", type=float, default=0.0002)
    p.add_argument("--no-funding", action="store_true", help="ignore funding costs")
    p.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help="override a strategy parameter, repeatable")
    p.add_argument("--json-out", help="write the full result JSON here")
    p.add_argument("--quiet", action="store_true", help="print only the summary JSON")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("demo", help="build the replay chart from a result JSON")
    p.add_argument("result", help="path to a --json-out file")
    p.add_argument("--out", help="output .html (default: alongside the result)")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("index", help="rebuild the run index page")
    p.add_argument("dir", nargs="?", default="results", help="results directory")
    p.set_defaults(func=cmd_index)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(message)s", stream=sys.stderr,
    )
    try:
        return args.func(args)
    except sync_mod.SyncError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
