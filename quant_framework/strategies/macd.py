"""MACD 趋势跟随策略实现。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from quant_framework.strategies.base import Signal, Strategy


@dataclass
class MACDConfig:
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    trade_size: float = 0.001


class MACDTrendStrategy(Strategy):
    """当 MACD 柱线由负转正/由正转负时切换持仓。"""

    def __init__(self, symbol: str, config: MACDConfig | None = None) -> None:
        super().__init__(symbol)
        self.config = config or MACDConfig()
        self.fast_ema: Optional[float] = None
        self.slow_ema: Optional[float] = None
        self.signal_line: Optional[float] = None
        self.prev_hist: Optional[float] = None

    def _ema(self, prev: Optional[float], price: float, period: int) -> float:
        alpha = 2 / (period + 1)
        if prev is None:
            return price
        return prev + alpha * (price - prev)

    def on_bar(self, bar) -> Optional[Signal]:
        close_price = bar[4] if isinstance(bar, (list, tuple)) else bar["close"]
        self.fast_ema = self._ema(self.fast_ema, close_price, self.config.fast_period)
        self.slow_ema = self._ema(self.slow_ema, close_price, self.config.slow_period)
        if self.fast_ema is None or self.slow_ema is None:
            return None
        macd = self.fast_ema - self.slow_ema
        self.signal_line = self._ema(self.signal_line, macd, self.config.signal_period)
        if self.signal_line is None:
            return None
        hist = macd - self.signal_line
        prev_hist = self.prev_hist
        self.prev_hist = hist
        if prev_hist is None:
            return None
        if hist > 0 and prev_hist <= 0:
            return Signal(symbol=self.symbol, side="buy", size=self.config.trade_size, price=close_price)
        if hist < 0 and prev_hist >= 0:
            return Signal(symbol=self.symbol, side="sell", size=self.config.trade_size, price=close_price)
        return None
