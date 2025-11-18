"""Minimal script to run a backtest without invoking the CLI."""
from __future__ import annotations

import csv
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_framework.backtesting import run_strategy_backtest
from quant_framework.strategies.macd import MACDTrendStrategy


def load_bars(path: Path):
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


def main() -> None:
    csv_path = PROJECT_ROOT / "data" / "sample_btcusdt_1h.csv"
    bars = list(load_bars(csv_path))
    result = run_strategy_backtest(
        MACDTrendStrategy,
        "BTC/USDT",
        bars,
        initial_capital=1000.0,
        fee_rate=0.0004,
        slippage=0.0005,
    )
    print(result.pretty_summary())
    for idx, trade in enumerate(result.trades, start=1):
        print(
            f"回测交易 #{idx}: {trade.signal.side} qty={trade.size:.6f} price={trade.price:.2f} "
            f"pnl={trade.pnl:.4f} ({trade.pnl_pct*100:+.2f}%)"
        )


if __name__ == "__main__":
    main()
