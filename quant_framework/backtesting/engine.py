"""Lightweight backtesting engine for bar-based strategies.

中文提示：提供无外部依赖的简易回测引擎，可直接复用策略逻辑验证结果。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List

from quant_framework.strategies.base import Signal, Strategy


@dataclass
class BacktestTrade:
    bar_index: int
    signal: Signal
    size: float
    price: float
    notional: float
    pnl: float
    pnl_pct: float
    equity_after_trade: float


@dataclass
class BacktestResult:
    trades: List[BacktestTrade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    final_equity: float = 0.0
    max_drawdown: float = 0.0
    total_return: float = 0.0
    win_rate: float = 0.0

    def summary(self) -> Dict[str, float]:
        """Return a metrics dict for quick pretty-printing or serialization."""

        return {
            "final_equity": self.final_equity,
            "total_return": self.total_return,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "trades": len(self.trades),
        }

    def pretty_summary(self) -> str:
        """Generate a human-readable summary string."""

        metrics = self.summary()
        return (
            "最终权益: {final_equity:.2f}, 总收益率: {total_return:.2%}, 最大回撤: {max_drawdown:.2%}, "
            "胜率: {win_rate:.2%}, 交易次数: {trades}"
        ).format(**metrics)


class BacktestEngine:
    def __init__(
        self,
        strategy: Strategy,
        initial_capital: float = 1000.0,
        fee_rate: float = 0.0,
        slippage: float = 0.0,
    ) -> None:
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.position = 0.0
        self.cash = initial_capital
        self.fee_rate = fee_rate
        self.slippage = slippage
        self.result = BacktestResult(equity_curve=[initial_capital], final_equity=initial_capital)

    def run(self, bars: Iterable) -> BacktestResult:
        for idx, bar in enumerate(bars):
            # 中文：遍历每一根 K 线，复用策略 on_bar 接口
            signal = self.strategy.on_bar(bar)
            close_price = bar[4] if isinstance(bar, (list, tuple)) else bar["close"]
            if signal:
                pnl, notional, exec_price, qty = self._apply_signal(signal, close_price)
                equity_after = self._current_equity(close_price)
                trade = BacktestTrade(
                    bar_index=idx,
                    signal=signal,
                    size=qty,
                    price=exec_price,
                    notional=notional,
                    pnl=pnl,
                    pnl_pct=(pnl / abs(notional)) if notional else 0.0,
                    equity_after_trade=equity_after,
                )
                self.result.trades.append(trade)
            self.result.equity_curve.append(self._current_equity(close_price))
        self.result.final_equity = self.result.equity_curve[-1]
        self.result.total_return = (self.result.final_equity - self.initial_capital) / self.initial_capital
        self.result.max_drawdown = self._compute_max_drawdown(self.result.equity_curve)
        self.result.win_rate = self._compute_win_rate()
        return self.result

    def _resolve_size(self, signal: Signal, price: float) -> float:
        """Derive tradable 数量 from Signal fields."""

        if signal.size is not None:
            return signal.size
        if signal.quote is not None:
            return signal.quote / price
        if signal.contracts is not None:
            return signal.contracts
        raise ValueError("Signal missing size/quote/contracts definition")

    def _apply_signal(self, signal: Signal, price: float) -> tuple[float, float, float, float]:
        qty = self._resolve_size(signal, price)
        exec_price = price
        if signal.side == "buy":
            exec_price *= 1 + self.slippage
        elif signal.side == "sell":
            exec_price *= 1 - self.slippage
        else:
            raise ValueError(f"Unsupported side {signal.side}")

        prev_equity = self._current_equity(price)

        if signal.side == "buy":
            cost = qty * exec_price
            fee = cost * self.fee_rate
            self.position += qty
            self.cash -= cost + fee
        else:  # sell
            proceeds = qty * exec_price
            fee = proceeds * self.fee_rate
            self.position -= qty
            self.cash += proceeds - fee

        pnl = self._current_equity(price) - prev_equity
        notional = qty * exec_price
        return pnl, notional, exec_price, qty

    def _current_equity(self, mark_price: float) -> float:
        return self.cash + self.position * mark_price

    def _compute_max_drawdown(self, curve: List[float]) -> float:
        peak = curve[0] if curve else 0.0
        max_dd = 0.0
        for equity in curve:
            if equity > peak:
                peak = equity
            if peak > 0:
                drawdown = (peak - equity) / peak
                max_dd = max(max_dd, drawdown)
        return max_dd

    def _compute_win_rate(self) -> float:
        if not self.result.trades:
            return 0.0
        winners = sum(1 for trade in self.result.trades if trade.pnl > 0)
        return winners / len(self.result.trades)
