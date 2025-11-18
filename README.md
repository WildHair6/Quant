# Quant Trading Framework

This repository contains a modular quantitative trading framework built around
[`ccxt`](https://github.com/ccxt/ccxt).  It focuses on keeping configuration,
strategy logic, market data access, trade execution, and backtesting separate so
that components can be reused across exchanges.

## Features

- Built-in exchange configs for **Binance**, **OKX**, and **Bitget**
- REST market data and trading via `ccxt`
- Direct WebSocket subscriptions for low-latency data feeds
- Strategy abstraction layer with multiple ready-to-run examples (MA cross,
  RSI、Donchian 突破、布林带、MACD、ATR 通道)
- Lightweight backtesting engine to quickly validate ideas
- Order sizing helper that aligns quantities/contract sizes and even supports
  USDT 名义金额直接换算
- Trade ledger + fill fetcher to capture every completed trade's profit and ROI

## 中文速览

- 内置 Binance / OKX / Bitget 配置，可快速切换交易所
- REST + WebSocket 行情源统一封装，便于策略自由组合
- 策略层提供基类与多种常见策略（均线/RSI/通道突破/布林带/MACD/ATR 通道），易于扩展
- 简易回测引擎可在不依赖外部平台的情况下验证思路
- CLI 提供「实盘 / WebSocket 监听 / 回测」三种模式，命令统一
- 下单模块支持自动对齐合约张数、最小下单量，并可根据 USDT 金额换算下单
- CLI `--dry-run` 模式可在没有 API Key 时直接运行，验证策略流程
- `--log-fills` 与 TradeLedger 可同步交易所成交并记录每笔盈亏

## Project Structure

```
quant_framework/
├── backtesting/          # Vector-free but composable bar backtester
├── config/               # Exchange configuration and credential helpers
├── data/                 # REST + WebSocket data feed clients
├── execution/            # Live trading orchestrator + pipeline building blocks
├── strategies/           # Base class + MA / RSI / Breakout / Bollinger 策略
└── utils/                # Logging utilities
```

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Credentials（可选）

现在可以直接使用一个独立文件集中存放所有交易所的 API：

```bash
cp api_keys.sample.json api_keys.json
# 打开 api_keys.json 将示例替换为自己的真实 Key / Secret / Passphrase
```

`quant_framework.config.exchanges` 会自动读取 `api_keys.json`，并为 Binance / OKX / Bitget
注入认证信息；若文件缺失则回退至环境变量和 `.env`。样例文件中已经放入了三大
交易所的字段格式，方便直接替换：

```json
{
  "binance": {"apiKey": "your_binance_api_key", "secret": "your_binance_api_secret"},
  "okx": {"apiKey": "your_okx_api_key", "secret": "your_okx_api_secret", "password": "your_okx_passphrase"},
  "bitget": {"apiKey": "your_bitget_api_key", "secret": "your_bitget_api_secret", "password": "your_bitget_passphrase"}
}
```

如果你更习惯使用环境变量，也可以继续：

```bash
export CCXT_BINANCE_API_KEY=xxx
export CCXT_BINANCE_API_SECRET=yyy
# OKX/Bitget 亦可按照 CCXT_<EXCHANGE>_API_KEY 命名规则设置
```

框架同样会在导入配置模块时自动查找 `.env` 文件并把里面的 `CCXT_*` 变量注入环境。
未配置凭证时，`python main.py live ...` 会自动进入 dry-run，仅记录信号。

### Live trading via REST

```bash
python main.py live BTC/USDT binance --timeframe 1m --poll 10 --strategy rsi --dry-run
```

This command polls Binance every 10 seconds for fresh OHLC candles, runs the
RSI strategy, and (unless `--dry-run` is provided) executes market orders when
signals are generated.

`--log-fills` 会在每次轮询后调用交易所的 `fetch_closed_orders` / `fetch_my_trades`，
将最新成交写入日志，便于与你的风控或记账系统对接。无论是否真实下单，`Trader`
内部的 `TradeLedger` 都会尝试以 FIFO 方式配对开平仓，并在日志中输出「盈亏 + 收益率」。

### 行情到下单的完整流水线

`quant_framework.execution.pipeline` 模块把实时交易拆成两个可复用的组件：

1. `MarketDataClient` 负责向交易所轮询最新 K 线并返回增量数据；
2. `OrderExecutor` 根据策略信号自动计算下单数量、控制精度，并调用 `ccxt` 创建订单。

`Trader` 在内部自动串联两者，你也可以在自定义脚本里直接组合它们。`examples/live_pipeline_dry_run.py`
提供了一个「拉取行情 -> 触发策略 -> 生成信号 -> 下单」的完整样例，只需 dry-run 即可验证：

```bash
python examples/live_pipeline_dry_run.py
```

运行后可在日志中看到实时行情、策略信号以及订单执行日志，便于你进一步扩展到正式交易。若补齐
API Key 并去掉 dry-run，便可在 Binance / OKX / Bitget 上完整走通「实盘拉行情至落地下单」的流程。
脚本结束时还会读取 `Trader.ledger.records`，以表格化的方式展示每笔配对后的收益率。

### WebSocket streaming

```bash
python main.py websocket BTCUSDT binance --channel trades --strategy breakout
```

Subscribes to trades on Binance via WebSocket and feeds ticks into the strategy
(`on_tick`).  The built-in strategies mainly react to bars, but this command
shows the streaming integration path.

### Built-in strategies

| Key        | Description (中文)                                    |
|------------|-------------------------------------------------------|
| `ma`       | 快慢均线交叉，适合趋势行情                           |
| `rsi`      | RSI 超买超卖反转                                     |
| `breakout` | Donchian 通道突破                                    |
| `bollinger`| 布林带双向均值回归                                   |
| `macd`     | MACD 柱线翻转趋势策略                                |
| `atr`      | ATR 通道突破，结合波动调整阈值                       |

### Backtesting

An example dataset is provided under `data/sample_btcusdt_1h.csv` so you can
start instantly:

```bash
python main.py backtest BTC/USDT data/sample_btcusdt_1h.csv --initial 1000 \
  --strategy macd --fee-rate 0.0004 --slippage 0.0005
```

The CLI now also reports cumulative return, win rate, and max drawdown so you
can quickly compare strategy robustness with configurable fee/slippage
assumptions.

- `--fee-rate`：设置每笔交易手续费（按比例），可模拟不同交易所成本；
- `--slippage`：设置单边滑点比例，便于评估极端行情或低流动性的影响。

所有回测交易会被记录在 `BacktestResult.trades`，其中包含触发信号、成交价格、
名义金额、`pnl` 与 `pnl_pct`（单笔收益率）。CLI 与 `examples/backtest_demo.py`
会逐笔打印这些指标，方便你快速验证策略质量或导出至其他分析工具。

除了 CLI，还可以在脚本或 Notebook 中直接调用回测模块与策略基类：

```python
from quant_framework.backtesting import run_strategy_backtest
from quant_framework.strategies.macd import MACDTrendStrategy

bars = ...  # 读取 CSV 或数据库中的 K 线
result = run_strategy_backtest(
    MACDTrendStrategy,
    "BTC/USDT",
    bars,
    initial_capital=1000,
    fee_rate=0.0004,
)
print(result.pretty_summary())
```

`examples/backtest_demo.py` 给出了一个可以直接运行的完整样例，默认读取
`data/sample_btcusdt_1h.csv` 并打印中文回测摘要。

### Flexible order sizing

- 策略可在 `Signal` 中同时支持 `size`（币数量）、`quote`（USDT 金额）或
  `contracts`（直接张数）。
- `Trader` 会自动：
  1. 根据当前行情或信号提供的价格，将 USDT 名义金额转换为基础币；
  2. 查询交易所 `contractSize`、最小下单量与精度，完成对齐；
  3. 通过 `ccxt` 市价单接口直接下单。

如需更细粒度控制，也可直接使用 `quant_framework.execution.pipeline.OrderExecutor` 来提交订单，
其返回的 `OrderResult` 包含最终数量、成交价格、订单 ID 等信息，便于日志与自定义风控。`Trader`
内部正是基于这些组件构建，确保你从行情拉取到下单的全链路都能单独测试与复用。

这意味着接入 Binance、OKX、Bitget 等合约/现货市场时，无需手工维护
不同品种的张数换算。

## Extending the framework

- Add new strategies by subclassing `quant_framework.strategies.base.Strategy`
- Build new exchange configs in `quant_framework.config.exchanges`
- Integrate custom execution logic inside `quant_framework.execution.trader`
- Enhance the backtester by enriching `quant_framework.backtesting.engine`
- Build custom ledgers/fill processors on top of `quant_framework.execution.pipeline.TradeLedger`
