"""Channel breakout strategy."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from quant_framework.strategies.base import Signal, Strategy


@dataclass
class BreakoutStrategyConfig:
    lookback: int = 20
    trade_size: float = 0.001
    breakout_buffer: float = 0.0  # 百分比缓冲，避免假突破


class DonchianBreakoutStrategy(Strategy):
    """监控最高价/最低价突破，兼容合约下单。"""

    def __init__(self, symbol: str, config: BreakoutStrategyConfig | None = None) -> None:
        super().__init__(symbol)
        self.config = config or BreakoutStrategyConfig()
        self.highs: Deque[float] = deque(maxlen=self.config.lookback)
        self.lows: Deque[float] = deque(maxlen=self.config.lookback)
        self.position: Optional[str] = None

    def on_bar(self, bar) -> Optional[Signal]:
        high = bar[2] if isinstance(bar, (list, tuple)) else bar["high"]
        low = bar[3] if isinstance(bar, (list, tuple)) else bar["low"]
        close_price = bar[4] if isinstance(bar, (list, tuple)) else bar["close"]
        self.highs.append(high)
        self.lows.append(low)
        if len(self.highs) < self.highs.maxlen:  # type: ignore[arg-type]
            return None
        channel_high = max(self.highs)
        channel_low = min(self.lows)
        buffer = self.config.breakout_buffer
        upper_trigger = channel_high * (1 + buffer)
        lower_trigger = channel_low * (1 - buffer)
        if close_price >= upper_trigger and self.position != "long":
            self.position = "long"
            return Signal(symbol=self.symbol, side="buy", size=self.config.trade_size, price=close_price)
        if close_price <= lower_trigger and self.position != "short":
            self.position = "short"
            return Signal(symbol=self.symbol, side="sell", size=self.config.trade_size, price=close_price)
        return None
