"""Composable building blocks for the live trading pipeline.

中文提示：该模块把行情获取、下单执行、成交记录整理成可复用组件，
帮助用户快速搭建 "拉取行情 -> 生成信号 -> 发送订单 -> 记录盈亏" 的完整流程。
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Sequence

from quant_framework.strategies.base import Signal


@dataclass
class MarketDataBatch:
    """Container for the latest一批 K 线数据。"""

    bars: Sequence[List[float]]
    last_timestamp: Optional[float]


class MarketDataClient:
    """Thin wrapper around ccxt OHLC 拉取逻辑。"""

    def __init__(self, client, symbol: str, timeframe: str, limit: int = 200) -> None:
        self.client = client
        self.symbol = symbol
        self.timeframe = timeframe
        self.limit = limit
        self.logger = logging.getLogger(__name__)

    async def fetch_new(self, last_timestamp: Optional[float]) -> MarketDataBatch:
        bars = await self.client.fetch_ohlcv(
            self.symbol, timeframe=self.timeframe, limit=self.limit
        )
        if not bars:
            self.logger.warning("未获取到 %s 的 %s K 线数据", self.symbol, self.timeframe)
            return MarketDataBatch([], last_timestamp)
        new_bars: List[List[float]] = []
        for bar in bars:
            ts = bar[0]
            if last_timestamp is None or ts > last_timestamp:
                new_bars.append(bar)
        if not new_bars:
            new_bars = [bars[-1]]
        return MarketDataBatch(new_bars, new_bars[-1][0])


@dataclass
class OrderResult:
    """标准化下单结果，便于日志与上层使用。"""

    signal: Signal
    amount: float
    price: float
    dry_run: bool
    response: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=lambda: time.time())


@dataclass
class FilledOrder:
    """统一的成交订单描述，方便记录与回放。"""

    id: Optional[str]
    symbol: str
    side: str
    price: float
    amount: float
    cost: float
    fee: Optional[float]
    status: Optional[str]
    timestamp: Optional[float]
    raw: Dict[str, Any]


@dataclass
class TradeRecord:
    """记录一次完整的开平仓，包含利润与收益率。"""

    symbol: str
    quantity: float
    entry_price: float
    exit_price: float
    profit: float
    profit_rate: float
    entry_side: str
    exit_side: str
    entry_timestamp: float
    exit_timestamp: float


@dataclass
class _OpenLeg:
    side: str
    qty: float
    price: float
    timestamp: float


class TradeLedger:
    """Pair fills to compute per-trade profit metrics.

    中文提示：该类以 FIFO 方式配对开仓与平仓，输出每笔完整交易的利润与收益率。
    """

    def __init__(self) -> None:
        self.open_longs: Deque[_OpenLeg] = deque()
        self.open_shorts: Deque[_OpenLeg] = deque()
        self.records: List[TradeRecord] = []

    def record_fill(self, result: OrderResult) -> List[TradeRecord]:
        qty = float(result.amount)
        if qty <= 0:
            return []
        side = result.signal.side
        if side == "buy":
            closed, qty = self._close_shorts(qty, result)
            if qty > 0:
                self.open_longs.append(_OpenLeg(side="buy", qty=qty, price=result.price, timestamp=result.timestamp))
            return closed
        elif side == "sell":
            closed, qty = self._close_longs(qty, result)
            if qty > 0:
                self.open_shorts.append(
                    _OpenLeg(side="sell", qty=qty, price=result.price, timestamp=result.timestamp)
                )
            return closed
        else:
            raise ValueError(f"Unsupported side {side}")

    def _close_longs(self, qty: float, exit_result: OrderResult) -> tuple[List[TradeRecord], float]:
        closed: List[TradeRecord] = []
        while qty > 0 and self.open_longs:
            leg = self.open_longs[0]
            closed_qty = min(qty, leg.qty)
            profit = (exit_result.price - leg.price) * closed_qty
            profit_rate = (exit_result.price - leg.price) / leg.price if leg.price else 0.0
            record = TradeRecord(
                symbol=exit_result.signal.symbol,
                quantity=closed_qty,
                entry_price=leg.price,
                exit_price=exit_result.price,
                profit=profit,
                profit_rate=profit_rate,
                entry_side=leg.side,
                exit_side=exit_result.signal.side,
                entry_timestamp=leg.timestamp,
                exit_timestamp=exit_result.timestamp,
            )
            closed.append(record)
            self.records.append(record)
            leg.qty -= closed_qty
            qty -= closed_qty
            if leg.qty == 0:
                self.open_longs.popleft()
        return closed, qty

    def _close_shorts(self, qty: float, exit_result: OrderResult) -> tuple[List[TradeRecord], float]:
        closed: List[TradeRecord] = []
        while qty > 0 and self.open_shorts:
            leg = self.open_shorts[0]
            closed_qty = min(qty, leg.qty)
            profit = (leg.price - exit_result.price) * closed_qty
            profit_rate = (leg.price - exit_result.price) / leg.price if leg.price else 0.0
            record = TradeRecord(
                symbol=exit_result.signal.symbol,
                quantity=closed_qty,
                entry_price=leg.price,
                exit_price=exit_result.price,
                profit=profit,
                profit_rate=profit_rate,
                entry_side=leg.side,
                exit_side=exit_result.signal.side,
                entry_timestamp=leg.timestamp,
                exit_timestamp=exit_result.timestamp,
            )
            closed.append(record)
            self.records.append(record)
            leg.qty -= closed_qty
            qty -= closed_qty
            if leg.qty == 0:
                self.open_shorts.popleft()
        return closed, qty


class OrderExecutor:
    """Handles order sizing, precision, and ccxt 下单调用。"""

    def __init__(self, exchange_config, client, markets: Optional[Dict[str, Any]] = None, *, dry_run: bool = False) -> None:
        self.exchange_config = exchange_config
        self.client = client
        self._markets = markets
        self.dry_run = dry_run or not exchange_config.credentials
        self.logger = logging.getLogger(__name__)

    def update_markets(self, markets: Dict[str, Any]) -> None:
        self._markets = markets

    async def execute(self, signal: Signal) -> OrderResult:
        if not self._markets:
            self._markets = await self.client.load_markets()
        market = self._markets.get(signal.symbol)
        if not market:
            raise ValueError(f"Symbol {signal.symbol} not available on exchange")
        price = signal.price or await self._fetch_last_price(signal.symbol)
        amount = self._calculate_exchange_amount(signal, price, market)
        if self.dry_run:
            self.logger.info(
                "[DRY-RUN] %s %s %.6f @ %.2f", signal.side.upper(), signal.symbol, amount, price
            )
            return OrderResult(signal=signal, amount=amount, price=price, dry_run=True)
        order_type = "market"
        response = await self.client.create_order(
            symbol=signal.symbol,
            type=order_type,
            side=signal.side,
            amount=amount,
            price=price,
            params={},
        )
        self.logger.info(
            "下单成功：%s %s %.6f @ %.2f (order_id=%s)",
            signal.side.upper(),
            signal.symbol,
            amount,
            price,
            response.get("id"),
        )
        timestamp = response.get("timestamp") if isinstance(response, dict) else None
        return OrderResult(
            signal=signal,
            amount=amount,
            price=price,
            dry_run=False,
            response=response,
            timestamp=float(timestamp) / 1000 if timestamp else time.time(),
        )

    async def _fetch_last_price(self, symbol: str) -> float:
        ticker = await self.client.fetch_ticker(symbol)
        price = ticker.get("last") or ticker.get("close") or ticker.get("bid") or ticker.get("ask")
        if price is None:
            raise ValueError(f"Unable to fetch reference price for {symbol}")
        return float(price)

    def _calculate_exchange_amount(self, signal: Signal, price: float, market: Dict[str, Any]) -> float:
        if signal.contracts is not None:
            qty = float(signal.contracts)
        else:
            if signal.size is not None:
                base_qty = float(signal.size)
            elif signal.quote is not None:
                base_qty = float(signal.quote / price)
            else:
                raise ValueError("Signal missing sizing information")
            if market.get("contract"):
                contract_size = (
                    market.get("contractSize")
                    or market.get("info", {}).get("ctVal")
                    or 1.0
                )
                qty = base_qty / float(contract_size)
            else:
                qty = base_qty
        qty = float(self.client.amount_to_precision(signal.symbol, qty))
        limits_root = market.get("limits", {})
        limits = limits_root.get("amount") or limits_root.get("contract") or {}
        min_amt = limits.get("min")
        max_amt = limits.get("max")
        if min_amt is not None:
            qty = max(qty, float(min_amt))
        if max_amt is not None:
            qty = min(qty, float(max_amt))
        return qty

    async def fetch_filled_orders(self, symbol: str, limit: int = 20) -> List[FilledOrder]:
        """Retrieve recently closed orders or成交 trades from the exchange.

        中文说明：调用 ``ccxt`` 的 ``fetch_closed_orders``/``fetch_my_trades``，
        返回统一结构，方便日志与本地持久化。
        """

        if self.dry_run:
            self.logger.debug("Dry-run 模式不会从交易所同步成交记录")
            return []
        orders: List[Dict[str, Any]] = []
        try:
            if hasattr(self.client, "fetch_closed_orders"):
                orders = await self.client.fetch_closed_orders(symbol, limit=limit)
            elif hasattr(self.client, "fetch_my_trades"):
                orders = await self.client.fetch_my_trades(symbol, limit=limit)
            else:
                self.logger.warning("交易所 %s 不支持成交订单查询", self.exchange_config.exchange_id)
                return []
        except Exception as exc:  # pragma: no cover - network errors
            self.logger.error("获取成交订单失败: %s", exc)
            return []
        return [self._normalize_filled_order(payload) for payload in orders]

    def _normalize_filled_order(self, payload: Dict[str, Any]) -> FilledOrder:
        fee: Optional[float] = None
        fee_info = payload.get("fee")
        if isinstance(fee_info, dict):
            fee_cost = fee_info.get("cost")
            fee = float(fee_cost) if fee_cost is not None else None
        elif isinstance(fee_info, (int, float)):
            fee = float(fee_info)
        cost = payload.get("cost")
        amount = payload.get("amount") or payload.get("filled") or 0.0
        price = payload.get("price") or payload.get("average") or 0.0
        if cost is None and amount and price:
            cost = float(amount) * float(price)
        return FilledOrder(
            id=payload.get("id"),
            symbol=payload.get("symbol", ""),
            side=payload.get("side", ""),
            price=float(price or 0.0),
            amount=float(amount or 0.0),
            cost=float(cost or 0.0),
            fee=fee,
            status=payload.get("status"),
            timestamp=payload.get("timestamp"),
            raw=payload,
        )
