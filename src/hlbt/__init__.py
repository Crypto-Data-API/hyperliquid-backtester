"""Hyperliquid backtester — real market data, honest costs, replayable results."""

from .backtester import Backtester, BacktestConfig, BacktestResult, Trade
from .strategy import Context, Position, Signal, Strategy

__version__ = "0.1.0"

__all__ = [
    "Backtester", "BacktestConfig", "BacktestResult", "Trade",
    "Context", "Position", "Signal", "Strategy",
]
