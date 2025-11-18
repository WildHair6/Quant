"""Bollinger band mean reversion strategy."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Deque, Optional

from quant_framework.strategies.base import Signal, Strategy


@dataclass
class BollingerConfig:
    period: int = 20
    num_std: float = 2.0
    trade_size: float = 0.001


class BollingerReversionStrategy(Strategy):
    """K 线触及上轨/下轨时反向操作。"""

    def __init__(self, symbol: str, config: BollingerConfig | None = None) -> None:
        super().__init__(symbol)
        self.config = config or BollingerConfig()
        self.closes: Deque[float] = deque(maxlen=self.config.period)

    def on_bar(self, bar) -> Optional[Signal]:
        close_price = bar[4] if isinstance(bar, (list, tuple)) else bar["close"]
        self.closes.append(close_price)
        if len(self.closes) < self.closes.maxlen:  # type: ignore[arg-type]
            return None
        avg = mean(self.closes)
        deviation = pstdev(self.closes)
        upper = avg + self.config.num_std * deviation
        lower = avg - self.config.num_std * deviation
        if close_price <= lower:
            return Signal(symbol=self.symbol, side="buy", size=self.config.trade_size, price=close_price)
        if close_price >= upper:
            return Signal(symbol=self.symbol, side="sell", size=self.config.trade_size, price=close_price)
        return None
