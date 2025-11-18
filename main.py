from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path
from typing import Iterable, List

from quant_framework.backtesting.engine import BacktestEngine
from quant_framework.config.exchanges import ExchangeConfig, default_exchange_configs
from quant_framework.data.feeds import WebsocketDataFeed, WebsocketSubscription
from quant_framework.execution.trader import Trader, TraderSettings
from quant_framework.strategies.atr_channel import ATRChannelStrategy
from quant_framework.strategies.bollinger import BollingerReversionStrategy
from quant_framework.strategies.breakout import DonchianBreakoutStrategy
from quant_framework.strategies.macd import MACDTrendStrategy
from quant_framework.strategies.moving_average import MovingAverageCrossStrategy
from quant_framework.strategies.rsi import RSIMomentumStrategy
from quant_framework.utils.logging import configure_logging


STRATEGY_BUILDERS = {
    "ma": MovingAverageCrossStrategy,
    "rsi": RSIMomentumStrategy,
    "breakout": DonchianBreakoutStrategy,
    "bollinger": BollingerReversionStrategy,
    "macd": MACDTrendStrategy,
    "atr": ATRChannelStrategy,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Modular ccxt trading framework")
    # 中文：命令行拆分为 live / websocket / backtest 三种模式
    subparsers = parser.add_subparsers(dest="command", required=True)

    live = subparsers.add_parser("live", help="Run strategy live via REST")
    live.add_argument("symbol", help="Trading pair, e.g. BTC/USDT")
    live.add_argument("exchange", choices=["binance", "okx", "bitget"])
    live.add_argument("--timeframe", default="1m")
    live.add_argument("--poll", dest="poll_interval", type=float, default=5.0)
    live.add_argument(
        "--strategy",
        default="ma",
        choices=sorted(STRATEGY_BUILDERS.keys()),
        help="选择策略（ma/rsi/breakout/bollinger/macd/atr）",
    )
    live.add_argument(
        "--dry-run",
        action="store_true",
        help="只记录信号不真实下单，默认会在缺少 API Key 时自动开启",
    )
    live.add_argument(
        "--log-fills",
        action="store_true",
        help="实盘模式下轮询交易所成交订单并写入日志，便于对账",
    )

    ws = subparsers.add_parser("websocket", help="Stream ticks via websocket")
    ws.add_argument("symbol")
    ws.add_argument("exchange", choices=["binance", "okx", "bitget"])
    ws.add_argument("--channel", default="trades")
    ws.add_argument(
        "--strategy",
        default="ma",
        choices=sorted(STRATEGY_BUILDERS.keys()),
    )

    backtest = subparsers.add_parser("backtest", help="Run strategy on historical CSV data")
    backtest.add_argument("symbol")
    backtest.add_argument("csv", type=Path, help="Path to OHLCV CSV file")
    backtest.add_argument("--initial", type=float, default=1000.0)
    backtest.add_argument(
        "--strategy",
        default="ma",
        choices=sorted(STRATEGY_BUILDERS.keys()),
    )
    backtest.add_argument(
        "--fee-rate",
        type=float,
        default=0.0004,
        help="手续费假设（默认 4bps）",
    )
    backtest.add_argument(
        "--slippage",
        type=float,
        default=0.0,
        help="单边滑点假设，按比例输入",
    )

    return parser.parse_args()


def load_csv_bars(path: Path) -> Iterable[List[float]]:
    """Load OHLCV rows from CSV.

    中文说明：将 CSV 行转为浮点数组，便于回测引擎直接消费。
    """
    with path.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield [
                float(row.get("timestamp", 0)),
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row["volume"]),
            ]


def build_strategy(symbol: str, name: str):
    """Instantiate内置策略。"""

    try:
        return STRATEGY_BUILDERS[name](symbol)
    except KeyError as exc:
        raise ValueError(f"Unknown strategy {name}") from exc


async def run_live(args: argparse.Namespace) -> None:
    logger = configure_logging(name="live")
    configs = default_exchange_configs()
    exchange_config = configs[args.exchange]
    strategy = build_strategy(args.symbol, args.strategy)
    dry_run = args.dry_run
    if not dry_run and not exchange_config.credentials:
        logger.warning(
            "未检测到 %s 的 API Key，已自动开启 dry-run 模式（仅日志不下单）", args.exchange
        )
        dry_run = True
    settings = TraderSettings(
        symbol=args.symbol,
        timeframe=args.timeframe,
        poll_interval=args.poll_interval,
        dry_run=dry_run,
        log_fills=args.log_fills,
    )
    async with Trader(exchange_config, strategy, settings) as trader:
        logger.info("Starting live trading on %s", args.exchange)
        logger.info("中文提示：请确保已配置 API Key 并了解实盘风险。")
        await trader.run_forever()


async def run_websocket(args: argparse.Namespace) -> None:
    logger = configure_logging(name="websocket")
    subscription = WebsocketSubscription(exchange=args.exchange, symbol=args.symbol, channel=args.channel)
    strategy = build_strategy(args.symbol, args.strategy)
    async with WebsocketDataFeed(subscription) as feed:
        logger.info("Listening to %s %s via websocket", args.exchange, args.symbol)
        logger.info("中文提示：该模式仅订阅行情，不会下单。")
        async for payload in feed.listen():
            signal = strategy.on_tick(payload)
            if signal:
                logger.info("Signal generated from websocket data: %s", signal)


def run_backtest(args: argparse.Namespace) -> None:
    logger = configure_logging(name="backtest")
    bars = list(load_csv_bars(args.csv))
    strategy = build_strategy(args.symbol, args.strategy)
    engine = BacktestEngine(
        strategy,
        initial_capital=args.initial,
        fee_rate=args.fee_rate,
        slippage=args.slippage,
    )
    result = engine.run(bars)
    logger.info(
        "Backtest completed: final equity %.2f (%.2f%%)",
        result.final_equity,
        result.total_return * 100,
    )
    logger.info(
        "Max drawdown %.2f%% | Win rate %.2f%% | Trades %d",
        result.max_drawdown * 100,
        result.win_rate * 100,
        len(result.trades),
    )
    logger.info("中文提示：可通过 --fee-rate 与 --slippage 模拟手续费/滑点影响。")
    for idx, trade in enumerate(result.trades, start=1):
        logger.info(
            "Trade #%d %s qty=%.6f price=%.2f pnl=%.4f (%+.2f%%)",
            idx,
            trade.signal.side.upper(),
            trade.size,
            trade.price,
            trade.pnl,
            trade.pnl_pct * 100,
        )


def main() -> None:
    args = parse_args()
    if args.command == "live":
        asyncio.run(run_live(args))
    elif args.command == "websocket":
        asyncio.run(run_websocket(args))
    elif args.command == "backtest":
        run_backtest(args)


if __name__ == "__main__":
    main()
