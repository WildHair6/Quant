"""High-level trading framework package."""
from quant_framework.config.exchanges import ExchangeConfig, ExchangeCredentials, default_exchange_configs
from quant_framework.strategies.atr_channel import ATRChannelStrategy
from quant_framework.strategies.bollinger import BollingerReversionStrategy
from quant_framework.strategies.breakout import DonchianBreakoutStrategy
from quant_framework.strategies.macd import MACDTrendStrategy
from quant_framework.strategies.moving_average import MovingAverageCrossStrategy
from quant_framework.strategies.rsi import RSIMomentumStrategy

__all__ = [
    "ExchangeConfig",
    "ExchangeCredentials",
    "default_exchange_configs",
    "MovingAverageCrossStrategy",
    "RSIMomentumStrategy",
    "DonchianBreakoutStrategy",
    "BollingerReversionStrategy",
    "MACDTrendStrategy",
    "ATRChannelStrategy",
]
