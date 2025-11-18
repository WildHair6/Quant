"""Reference moving average cross strategy.

中文提示：示范快慢均线策略实现，便于理解框架的策略开发流程。
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from quant_framework.strategies.base import Signal, Strategy


@dataclass
class MovingAverageConfig:
    fast_period: int = 5
    slow_period: int = 20
    trade_size: float = 0.001


class MovingAverageCrossStrategy(Strategy):
    def __init__(self, symbol: str, config: MovingAverageConfig | None = None) -> None:
        super().__init__(symbol)
        self.config = config or MovingAverageConfig()
        self.fast_window: Deque[float] = deque(maxlen=self.config.fast_period)
        self.slow_window: Deque[float] = deque(maxlen=self.config.slow_period)
        self.last_position: Optional[str] = None

    def _update_moving_average(self, window: Deque[float], price: float) -> Optional[float]:
        window.append(price)
        # 中文：窗口未填满前不返回数值，避免提前交易
        if len(window) < window.maxlen:  # type: ignore[arg-type]
            return None
        return sum(window) / len(window)

    def on_bar(self, bar) -> Optional[Signal]:
        close_price = bar[4] if isinstance(bar, (list, tuple)) else bar["close"]
        # 中文：更新快慢均线
        fast = self._update_moving_average(self.fast_window, close_price)
        slow = self._update_moving_average(self.slow_window, close_price)

        if fast is None or slow is None:
            return None

        if fast > slow and self.last_position != "long":
            self.last_position = "long"
            # 中文：快线上穿慢线，构建做多信号
            return Signal(symbol=self.symbol, side="buy", size=self.config.trade_size, price=close_price)
        if fast < slow and self.last_position != "short":
            self.last_position = "short"
            # 中文：快线下穿慢线，构建做空信号
            return Signal(symbol=self.symbol, side="sell", size=self.config.trade_size, price=close_price)
        return None
