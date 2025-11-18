"""Strategy abstractions.

中文提示：提供信号数据结构与策略抽象基类，所有策略需继承此接口。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    """Standardized trading signal container.

    中文说明：统一描述策略发出的下单需求，支持币数量、USDT 名义金额
    以及直接指定合约张数，方便执行层按需转换。
    """

    symbol: str
    side: str  # "buy" or "sell"
    size: Optional[float] = None  # 以基础币计量的下单数量
    price: Optional[float] = None
    quote: Optional[float] = None  # 以报价币（如 USDT）计量的下单金额
    contracts: Optional[float] = None  # 直接下指定张数


class Strategy(ABC):
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    @abstractmethod
    def on_bar(self, bar) -> Optional[Signal]:
        """Process OHLCV bar data and optionally emit a :class:`Signal`.

        中文说明：在收到每根 K 线时执行交易逻辑，返回信号或 ``None``。
        """

    def on_tick(self, tick) -> Optional[Signal]:
        """Optional real-time tick handler for websocket data.

        中文说明：WebSocket 推送时可复写该方法，实现更细粒度的实时响应。
        """
        return None
