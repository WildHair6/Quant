"""RSI momentum strategy implementation."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from quant_framework.strategies.base import Signal, Strategy


@dataclass
class RSIStrategyConfig:
    period: int = 14
    overbought: float = 70
    oversold: float = 30
    trade_size: float = 0.001


class RSIMomentumStrategy(Strategy):
    """Use相对强弱指标过滤多空信号。"""

    def __init__(self, symbol: str, config: RSIStrategyConfig | None = None) -> None:
        super().__init__(symbol)
        self.config = config or RSIStrategyConfig()
        self.closes: Deque[float] = deque(maxlen=self.config.period + 1)

    def _compute_rsi(self) -> Optional[float]:
        if len(self.closes) <= self.config.period:
            return None
        gains = 0.0
        losses = 0.0
        closes = list(self.closes)
        for prev, curr in zip(closes[:-1], closes[1:]):
            delta = curr - prev
            if delta >= 0:
                gains += delta
            else:
                losses -= delta
        avg_gain = gains / self.config.period
        avg_loss = losses / self.config.period if losses else 1e-9
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def on_bar(self, bar) -> Optional[Signal]:
        close_price = bar[4] if isinstance(bar, (list, tuple)) else bar["close"]
        self.closes.append(close_price)
        rsi = self._compute_rsi()
        if rsi is None:
            return None
        if rsi < self.config.oversold:
            return Signal(symbol=self.symbol, side="buy", size=self.config.trade_size, price=close_price)
        if rsi > self.config.overbought:
            return Signal(symbol=self.symbol, side="sell", size=self.config.trade_size, price=close_price)
        return None
