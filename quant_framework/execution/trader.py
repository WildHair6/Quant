"""Live trading orchestrator.

中文提示：负责轮询行情、触发策略、执行订单的整体流程控制。
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Optional, TYPE_CHECKING

try:  # pragma: no cover - optional dependency
    import ccxt.async_support as ccxt_async  # type: ignore
except ImportError:  # pragma: no cover
    ccxt_async = None  # type: ignore

if TYPE_CHECKING:  # pragma: no cover
    from ccxt.async_support import Exchange as AsyncExchange
else:
    AsyncExchange = Any

from quant_framework.config.exchanges import ExchangeConfig
from quant_framework.execution.pipeline import MarketDataClient, OrderExecutor, TradeLedger
from quant_framework.strategies.base import Signal, Strategy


@dataclass
class TraderSettings:
    symbol: str
    timeframe: str = "1m"
    ohlcv_limit: int = 200
    poll_interval: float = 5.0
    dry_run: bool = False
    log_fills: bool = False


class Trader:
    """Coordinates data fetching, strategy evaluation, and order execution.

    中文说明：封装交易循环，确保在统一的异步任务中完成行情拉取与下单。
    """

    def __init__(self, exchange_config: ExchangeConfig, strategy: Strategy, settings: TraderSettings) -> None:
        self.exchange_config = exchange_config
        self.strategy = strategy
        self.settings = settings
        self.exchange: Optional[AsyncExchange] = None
        self.markets: Dict[str, Any] | None = None
        self.logger = logging.getLogger(__name__)
        self._last_bar_timestamp: Optional[float] = None
        self._data_client: Optional[MarketDataClient] = None
        self._order_executor: Optional[OrderExecutor] = None
        self._ledger = TradeLedger()
        self._recent_fill_ids: Deque[str] = deque(maxlen=200)

    async def __aenter__(self) -> "Trader":
        # 中文：进入上下文时初始化交易所连接
        if ccxt_async is None:
            raise RuntimeError("ccxt 未安装，无法运行 live/websocket 模式，请先安装依赖")
        self.exchange = self.exchange_config.create_rest_client()
        self.markets = await self.exchange.load_markets()
        self._data_client = MarketDataClient(
            self.exchange,
            symbol=self.settings.symbol,
            timeframe=self.settings.timeframe,
            limit=self.settings.ohlcv_limit,
        )
        self._order_executor = OrderExecutor(
            self.exchange_config,
            self.exchange,
            markets=self.markets,
            dry_run=self.settings.dry_run,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        if self.exchange:
            await self.exchange.close()

    @property
    def client(self) -> AsyncExchange:
        if not self.exchange:
            raise RuntimeError("Trader has not been initialized. Use 'async with Trader'.")
        return self.exchange

    @property
    def ledger(self) -> TradeLedger:
        return self._ledger

    async def run_forever(self) -> None:
        while True:
            # 中文：run_forever 通过定时睡眠实现轮询
            await self.run_once()
            await asyncio.sleep(self.settings.poll_interval)

    async def run_once(self) -> None:
        if not self._data_client:
            raise RuntimeError("Trader 未初始化 MarketDataClient")
        batch = await self._data_client.fetch_new(self._last_bar_timestamp)
        if not batch.bars:
            self.logger.warning("未从交易所获取到 K 线数据，稍后重试")
            return
        for bar in batch.bars:
            signal = self.strategy.on_bar(bar)
            if signal:
                await self.execute_signal(signal)
        self._last_bar_timestamp = batch.last_timestamp
        if self.settings.log_fills and not self.settings.dry_run:
            await self.log_recent_fills()

    async def execute_signal(self, signal: Signal) -> None:
        if not self._order_executor:
            raise RuntimeError("Trader 未初始化 OrderExecutor")
        result = await self._order_executor.execute(signal)
        if result.dry_run:
            self.logger.debug("Dry-run order result: %s", result)
        closed = self._ledger.record_fill(result)
        for record in closed:
            self.logger.info(
                "%s 平仓 数量 %.6f | 盈亏 %.4f (%+.2f%%)%s",
                record.symbol,
                record.quantity,
                record.profit,
                record.profit_rate * 100,
                " [DRY-RUN]" if result.dry_run else "",
            )

    async def log_recent_fills(self) -> None:
        if not self._order_executor:
            return
        fills = await self._order_executor.fetch_filled_orders(self.settings.symbol, limit=20)
        for fill in fills:
            fill_id = fill.id or f"{fill.timestamp}-{fill.side}-{fill.price}-{fill.amount}"
            if fill_id in self._recent_fill_ids:
                continue
            if self._recent_fill_ids.maxlen and len(self._recent_fill_ids) == self._recent_fill_ids.maxlen:
                self._recent_fill_ids.popleft()
            self._recent_fill_ids.append(fill_id)
            self.logger.info(
                "成交订单 %s %s %.6f @ %.2f | 成交额 %.2f | 手续费 %s",
                fill.symbol,
                fill.side.upper(),
                fill.amount,
                fill.price,
                fill.cost,
                fill.fee,
            )
