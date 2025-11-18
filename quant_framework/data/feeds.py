"""Market data feed abstractions.

中文提示：统一封装 REST 与 WebSocket 行情源，便于策略模块按需订阅行情。
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Optional, TYPE_CHECKING

try:  # pragma: no cover - optional dependency for REST
    import ccxt.async_support as ccxt_async  # type: ignore
except ImportError:  # pragma: no cover
    ccxt_async = None  # type: ignore

if TYPE_CHECKING:  # pragma: no cover
    from ccxt.async_support import Exchange as AsyncExchange
else:
    AsyncExchange = Any

try:  # pragma: no cover - optional dependency for websocket mode
    import websockets
except ImportError:  # pragma: no cover
    websockets = None  # type: ignore

from quant_framework.config.exchanges import ExchangeConfig


class RESTDataFeed:
    """Simple wrapper around a ``ccxt`` asynchronous client.

    中文说明：最小封装 ccxt 异步客户端，适合轮询 OHLC/K 线与 Ticker 数据。
    """

    def __init__(
        self,
        exchange_config: ExchangeConfig,
        symbol: str,
        timeframe: str = "1m",
    ) -> None:
        self.config = exchange_config
        self.symbol = symbol
        self.timeframe = timeframe
        self._client: Optional[AsyncExchange] = None

    async def __aenter__(self) -> "RESTDataFeed":
        # 中文：在异步上下文中创建 ccxt 客户端，确保退出时能够自动关闭连接
        self._client = self.config.create_rest_client()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        if self._client:
            await self._client.close()

    @property
    def client(self) -> AsyncExchange:
        if not self._client:
            raise RuntimeError("Data feed not initialized. Use 'async with RESTDataFeed'.")
        # 中文：client 属性只会在 __aenter__ 成功后才可用，防止误用
        return self._client

    async def fetch_ohlcv(self, limit: int = 200) -> Any:
        # 中文：封装 ccxt 的 fetch_ohlcv，默认取 200 根 K 线
        return await self.client.fetch_ohlcv(self.symbol, timeframe=self.timeframe, limit=limit)

    async def fetch_ticker(self) -> Any:
        # 中文：可用于更实时的价量信息
        return await self.client.fetch_ticker(self.symbol)


@dataclass
class WebsocketSubscription:
    exchange: str
    symbol: str
    channel: str = "trades"


class WebsocketDataFeed:
    """Websocket helper that knows how to subscribe to multiple exchanges.

    中文说明：针对不同交易所的订阅格式差异，统一封装订阅参数与连接生命周期。
    """

    WS_ENDPOINTS: Dict[str, str] = {
        "binance": "wss://stream.binance.com:9443/ws",
        "okx": "wss://ws.okx.com:8443/ws/v5/public",
        "bitget": "wss://ws.bitget.com/v2/ws/public",
    }

    def __init__(self, subscription: WebsocketSubscription) -> None:
        self.subscription = subscription
        self._connection: Optional[websockets.WebSocketClientProtocol] = None

    async def __aenter__(self) -> "WebsocketDataFeed":
        uri = self.WS_ENDPOINTS[self.subscription.exchange]
        # 中文：统一设置 ping 周期与超时，避免连接被动断开
        if websockets is None:
            raise RuntimeError("websockets 库未安装，无法使用实时订阅，请先安装依赖")
        self._connection = await websockets.connect(uri, ping_interval=20, ping_timeout=20)
        await self.subscribe()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        if self._connection and not self._connection.closed:
            await self._connection.close()

    @property
    def connection(self) -> websockets.WebSocketClientProtocol:
        if not self._connection:
            raise RuntimeError("Websocket not connected. Use 'async with WebsocketDataFeed'.")
        return self._connection

    async def subscribe(self) -> None:
        payload = self._build_subscription_payload()
        # 中文：不同交易所协议不一致，通过辅助方法生成订阅体
        await self.connection.send(json.dumps(payload))

    def _build_subscription_payload(self) -> Dict[str, Any]:
        symbol = self.subscription.symbol
        channel = self.subscription.channel
        exchange = self.subscription.exchange

        if exchange == "binance":
            # Binance expects lowercase symbols with @channel notation.
            stream = f"{symbol.lower()}@{channel}"
            return {"method": "SUBSCRIBE", "params": [stream], "id": 1}
        if exchange == "okx":
            return {
                "op": "subscribe",
                "args": [{"channel": channel, "instId": symbol.replace("/", "-")}],
            }
        if exchange == "bitget":
            return {
                "op": "subscribe",
                "args": [{"instType": "sp", "channel": channel, "instId": symbol.replace("/", "").upper()}],
            }
        raise ValueError(f"Unsupported exchange for websocket subscription: {exchange}")

    async def listen(self) -> AsyncIterator[Dict[str, Any]]:
        while True:
            # 中文：若连接被动关闭则等待重连机会
            if not self.connection.open:
                await asyncio.sleep(0.5)
                continue
            message = await self.connection.recv()
            yield json.loads(message)
