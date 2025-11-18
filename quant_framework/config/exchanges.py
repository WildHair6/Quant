"""Exchange configuration helpers for ccxt-based trading bots.

This module keeps exchange specific settings isolated from the rest of the
framework so that strategy and orchestration code can be reused across multiple
venues.  Each :class:`ExchangeConfig` can spawn both REST and WebSocket clients.

中文提示：该模块专注于交易所配置与凭证管理，确保策略与执行代码能够解耦复用。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

try:  # pragma: no cover - optional dependency at runtime
    import ccxt.async_support as ccxt_async  # type: ignore
except ImportError:  # pragma: no cover
    ccxt_async = None  # type: ignore

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ccxt.async_support import Exchange as AsyncExchange
else:
    AsyncExchange = Any


_DOTENV_LOADED = False
_API_FILE_LOADED = False
_API_FILE_CREDENTIALS: Dict[str, ExchangeCredentials] = {}


def _load_env_file() -> None:
    """Populate ``os.environ`` from ``.env`` if present."""

    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    root = Path(__file__).resolve().parents[2]
    env_file = root / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip('"')
    _DOTENV_LOADED = True


_load_env_file()


@dataclass
class ExchangeCredentials:
    """API credential container.

    中文说明：封装各交易所需要的 API Key / Secret / Password 等认证参数。
    """

    api_key: str
    secret: str
    password: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExchangeConfig:
    """Configuration blob for an exchange supported by ``ccxt``.

    Parameters
    ----------
    exchange_id:
        ``ccxt`` identifier (e.g. ``"binance"``).
    credentials:
        Optional :class:`ExchangeCredentials` so the same class can be used for
        public-only data feeds as well as authenticated trading sessions.
    options:
        Additional arguments forwarded to the ``ccxt`` constructor.
    enable_rate_limit:
        Whether to enable the built-in rate limiter.  It is generally a good idea
        to keep this ``True`` when live-trading.

    中文说明：该数据类汇总所有与单个交易所相关的初始化选项，方便在不同场景
    （行情拉取、下单、回测模拟）之间共享。
    """

    exchange_id: str
    credentials: Optional[ExchangeCredentials] = None
    options: Dict[str, Any] = field(default_factory=dict)
    enable_rate_limit: bool = True

    def create_rest_client(self) -> AsyncExchange:
        """Instantiate an asynchronous ``ccxt`` client for REST requests.

        中文说明：根据配置动态创建异步 ccxt REST 客户端，便于在不同协程中复用。
        """

        if ccxt_async is None:
            raise RuntimeError("ccxt 未安装，请先执行 'pip install -r requirements.txt'")
        exchange_class = getattr(ccxt_async, self.exchange_id)
        kwargs: Dict[str, Any] = {
            "enableRateLimit": self.enable_rate_limit,
            **self.options,
        }

        if self.credentials:
            kwargs.update(
                {
                    "apiKey": self.credentials.api_key,
                    "secret": self.credentials.secret,
                }
            )
            if self.credentials.password:
                kwargs["password"] = self.credentials.password
            if self.credentials.params:
                kwargs.update(self.credentials.params)

        return exchange_class(kwargs)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ExchangeConfig":
        creds_payload = payload.get("credentials")
        credentials = None
        if creds_payload:
            credentials = ExchangeCredentials(
                api_key=creds_payload["apiKey"],
                secret=creds_payload["secret"],
                password=creds_payload.get("password"),
                params=creds_payload.get("params", {}),
            )
        return cls(
            exchange_id=payload["id"],
            credentials=credentials,
            options=payload.get("options", {}),
            enable_rate_limit=payload.get("enable_rate_limit", True),
        )


def _load_api_file() -> None:
    """Read ``api_keys.json`` for credentials and cache them."""

    global _API_FILE_LOADED
    if _API_FILE_LOADED:
        return
    root = Path(__file__).resolve().parents[2]
    api_file = root / "api_keys.json"
    if not api_file.exists():
        _API_FILE_LOADED = True
        return
    try:
        payload = json.loads(api_file.read_text())
    except json.JSONDecodeError as exc:  # pragma: no cover - configuration error
        raise RuntimeError(f"api_keys.json 格式错误：{exc}") from exc

    for name, creds in payload.items():
        api_key = creds.get("apiKey")
        secret = creds.get("secret")
        if not api_key or not secret:
            continue
        _API_FILE_CREDENTIALS[name.lower()] = ExchangeCredentials(
            api_key=api_key,
            secret=secret,
            password=creds.get("password"),
            params=creds.get("params", {}),
        )
    _API_FILE_LOADED = True


def _file_credentials(exchange: str) -> Optional[ExchangeCredentials]:
    """Load credentials from ``api_keys.json`` if present."""

    _load_api_file()
    return _API_FILE_CREDENTIALS.get(exchange.lower())


def _env_credentials(exchange: str) -> Optional[ExchangeCredentials]:
    """Attempt to hydrate credentials from环境变量."""

    prefix = f"CCXT_{exchange.upper()}"
    api_key = os.getenv(f"{prefix}_API_KEY")
    secret = os.getenv(f"{prefix}_API_SECRET")
    password = os.getenv(f"{prefix}_API_PASSWORD")
    if not api_key or not secret:
        return None
    return ExchangeCredentials(api_key=api_key, secret=secret, password=password)


def _credentials_for_exchange(exchange: str) -> Optional[ExchangeCredentials]:
    """Choose credentials from file first, then fall back to env vars."""

    return _file_credentials(exchange) or _env_credentials(exchange)


def default_exchange_configs() -> Dict[str, ExchangeConfig]:
    """Provide baseline configuration for Binance, OKX, and Bitget.

    中文说明：返回框架内置的三大交易所默认配置，并自动尝试读取 ``CCXT_*``
    环境变量中的 API Key，若缺失则以只读方式运行。
    """

    configs: Dict[str, ExchangeConfig] = {}
    for name in ("binance", "okx", "bitget"):
        configs[name] = ExchangeConfig(exchange_id=name, credentials=_credentials_for_exchange(name))
    return configs
