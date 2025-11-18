"""ATR 通道策略：结合 ATR 波动与均线判断突破。"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import mean
from typing import Deque, Optional

from quant_framework.strategies.base import Signal, Strategy


@dataclass
class ATRChannelConfig:
    atr_period: int = 14
    baseline_period: int = 20
    atr_multiplier: float = 1.5
    trade_size: float = 0.001


class ATRChannelStrategy(Strategy):
    """当收盘价突破均线 ± ATR*N 时入场。"""

    def __init__(self, symbol: str, config: ATRChannelConfig | None = None) -> None:
        super().__init__(symbol)
        self.config = config or ATRChannelConfig()
        self.highs: Deque[float] = deque(maxlen=self.config.atr_period)
        self.lows: Deque[float] = deque(maxlen=self.config.atr_period)
        self.closes: Deque[float] = deque(maxlen=self.config.baseline_period)
        self.prev_close: Optional[float] = None
        self.true_ranges: Deque[float] = deque(maxlen=self.config.atr_period)

    def _true_range(self, high: float, low: float, prev_close: Optional[float]) -> float:
        if prev_close is None:
            return high - low
        return max(high - low, abs(high - prev_close), abs(low - prev_close))

    def _average_true_range(self) -> Optional[float]:
        if len(self.true_ranges) < self.true_ranges.maxlen:  # type: ignore[arg-type]
            return None
        return sum(self.true_ranges) / len(self.true_ranges)

    def on_bar(self, bar) -> Optional[Signal]:
        high = bar[2] if isinstance(bar, (list, tuple)) else bar["high"]
        low = bar[3] if isinstance(bar, (list, tuple)) else bar["low"]
        close_price = bar[4] if isinstance(bar, (list, tuple)) else bar["close"]
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close_price)
        tr = self._true_range(high, low, self.prev_close)
        self.true_ranges.append(tr)
        self.prev_close = close_price
        atr = self._average_true_range()
        if atr is None or len(self.closes) < self.closes.maxlen:  # type: ignore[arg-type]
            return None
        baseline = mean(self.closes)
        upper = baseline + self.config.atr_multiplier * atr
        lower = baseline - self.config.atr_multiplier * atr
        if close_price >= upper:
            return Signal(symbol=self.symbol, side="buy", size=self.config.trade_size, price=close_price)
        if close_price <= lower:
            return Signal(symbol=self.symbol, side="sell", size=self.config.trade_size, price=close_price)
        return None
