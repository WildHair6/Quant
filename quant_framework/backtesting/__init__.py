"""Convenience helpers for running backtests programmatically."""
from __future__ import annotations

from typing import Sequence, Type, TypeVar

from quant_framework.backtesting.engine import BacktestEngine, BacktestResult, BacktestTrade
from quant_framework.strategies.base import Strategy

StrategyCls = TypeVar("StrategyCls", bound=Strategy)


def run_strategy_backtest(
    strategy_cls: Type[StrategyCls],
    symbol: str,
    bars: Sequence,
    *,
    initial_capital: float = 1000.0,
    fee_rate: float = 0.0,
    slippage: float = 0.0,
) -> BacktestResult:
    """Instantiate ``strategy_cls`` and run a bar backtest.

    中文说明：示例化策略、执行回测、返回包含收益/回撤/胜率等指标的结果，便于在脚本
    或 Jupyter Notebook 中直接调用，而无需走 CLI。
    """

    strategy = strategy_cls(symbol)
    engine = BacktestEngine(
        strategy,
        initial_capital=initial_capital,
        fee_rate=fee_rate,
        slippage=slippage,
    )
    return engine.run(bars)


__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "BacktestTrade",
    "run_strategy_backtest",
]
