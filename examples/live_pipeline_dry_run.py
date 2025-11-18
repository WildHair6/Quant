"""Demonstrate the end-to-end pipeline from fetching行情 to submitting orders.

中文说明：示例脚本会以 dry-run 模式运行一次完整的 "拉取 K 线 -> 触发策略 -> 生成信号 -> 下单" 流程。
请先安装 requirements.txt 中的依赖，并确保网络可访问交易所公共行情接口。
"""
from __future__ import annotations

import asyncio

from quant_framework.config.exchanges import default_exchange_configs
from quant_framework.execution.trader import Trader, TraderSettings
from quant_framework.strategies.moving_average import MovingAverageCrossStrategy


async def main() -> None:
    configs = default_exchange_configs()
    exchange = configs["binance"]
    strategy = MovingAverageCrossStrategy("BTC/USDT")
    settings = TraderSettings(
        symbol="BTC/USDT",
        timeframe="1m",
        poll_interval=0.0,
        dry_run=True,
        ohlcv_limit=200,
        log_fills=True,
    )
    async with Trader(exchange, strategy, settings) as trader:
        await trader.run_once()
        if trader.ledger.records:
            for record in trader.ledger.records:
                print(
                    f"Ledger记录: {record.symbol} qty={record.quantity:.6f} entry={record.entry_price:.2f} "
                    f"exit={record.exit_price:.2f} profit={record.profit:.4f} ({record.profit_rate*100:+.2f}%)"
                )
        else:
            print("本次示例未触发完整的开平仓信号，可多运行几次或调整策略参数。")


if __name__ == "__main__":
    asyncio.run(main())
