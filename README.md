# Trading System - OpenAlgo + AITRAPP Integration

Complete trading system combining OpenAlgo strategies with AITRAPP backtest engine for strategy ranking and deployment.

## 🎯 Overview

This repository contains:
- **OpenAlgo Trading Strategies**: Production-ready strategies for NIFTY, SENSEX, and MCX
- **AITRAPP Backtest Engine**: Historical backtesting and strategy ranking system
- **Integration Layer**: Adapters and mocks to bridge OpenAlgo strategies with AITRAPP

## 📁 Repository Structure

```
.
├── openalgo/
│   └── strategies/
│       ├── scripts/          # Trading strategies
│       ├── adapters/         # AITRAPP strategy adapters
│       ├── utils/            # Integration utilities
│       ├── config/           # Backtest configuration
│       └── docs/             # Documentation
├── AITRAPP/
│   └── AITRAPP/
│       ├── packages/core/    # Core backtest engine
│       │   ├── backtest.py   # BacktestEngine
│       │   ├── historical_data.py  # HistoricalDataLoader
│       │   └── strategies/   # Strategy base classes
│       └── configs/          # Configuration files
└── README.md
```

## 🚀 Quick Start

### Prerequisites

```bash
pip install pyyaml structlog pandas numpy scipy httpx pydantic-settings h2
```

### Running Backtests

```bash
cd openalgo/strategies
python3 scripts/run_backtest_ranking.py \
    --symbol NIFTY \
    --start-date 2025-08-15 \
    --end-date 2025-11-10 \
    --capital 1000000
```

### Deploying Strategies

```bash
cd openalgo/strategies
bash scripts/deploy_ranked_strategies.sh
```

## 📊 Strategies Included

### NIFTY Strategies
- NIFTY Greeks Enhanced
- NIFTY Multi-Strike Momentum
- NIFTY Intraday Options Trend
- NIFTY Iron Condor
- NIFTY Gamma Scalping

### SENSEX Strategies
- SENSEX Greeks Enhanced
- SENSEX Multi-Strike Momentum
- SENSEX Intraday Options Trend

### MCX Strategies
- MCX Commodity Momentum Strategy

## 🔧 Key Components

### AITRAPP Integration
- `utils/aitrapp_integration.py`: Sets up AITRAPP path and imports
- `utils/openalgo_mock.py`: Mocks OpenAlgo API for backtesting
- `utils/strategy_adapter.py`: Base adapter for strategy conversion

### Backtest Engine
- `AITRAPP/AITRAPP/packages/core/backtest.py`: Main backtest engine
- `AITRAPP/AITRAPP/packages/core/historical_data.py`: Historical data loader
- `AITRAPP/AITRAPP/packages/core/strategies/base.py`: Strategy interface

## 📚 Documentation

- `openalgo/strategies/BACKTEST_README.md`: Backtest setup guide
- `openalgo/strategies/AITRAPP_INTEGRATION_GUIDE.md`: Integration details
- `openalgo/strategies/QUICKSTART.md`: Quick start guide

## 🔐 Configuration

Set environment variables (use placeholders, do not commit secrets):
```bash
export OPENALGO_APIKEY="YOUR_OPENALGO_APIKEY"
export DATABASE_URL="YOUR_DATABASE_URL"
```

### Dual OpenAlgo Instances (Kite for NSE/MCX, Dhan for Options)

We run two OpenAlgo servers to avoid broker conflicts:

1) **KiteConnect instance** (NSE/MCX strategies)
- Host: `http://127.0.0.1:5001`
- Env (in `.env` or shell):
  - `BROKER_API_KEY` / `BROKER_API_SECRET` for Kite
  - `REDIRECT_URL=http://127.0.0.1:5001/zerodha/callback`
  - `FLASK_PORT=5001`

2) **Dhan instance** (options strategies, options ranker)
- Host: `http://127.0.0.1:5002`
- Env (in a separate shell or a second .env file):
  - `BROKER_API_KEY` / `BROKER_API_SECRET` for Dhan
  - `REDIRECT_URL=http://127.0.0.1:5002/dhan/callback`
  - `FLASK_PORT=5002`

**Strategy routing**
- NSE/MCX strategies point to: `http://127.0.0.1:5001`
- Options strategies point to: `http://127.0.0.1:5002`

### OpenAlgo API Key Usage
All strategies require `OPENALGO_APIKEY`. This should be injected via:
- `openalgo/strategies/strategy_env.json` (per strategy), or
- runtime env vars when starting strategies.

### Ports Summary
- **5001**: OpenAlgo + KiteConnect (NSE/MCX)
- **5002**: OpenAlgo + Dhan (Options)

## 📝 License

See individual component licenses.

## 🤝 Contributing

This is a private trading system. For questions or issues, contact the repository owner.

## 📌 Trading Style (Operational Summary)

We use a **multi-strategy, multi-asset** approach with broker separation:

- **NSE/MCX intraday momentum + trend strategies**
  - Focus on trend strength (ADX), momentum (RSI/MACD), and volatility filters.
  - Risk per trade is capped and position sizing is volatility-adjusted.
  - Trades are managed with staged take‑profits and trailing stops.

- **Options strategies (ranked spreads and neutral setups)**
  - Use rankers to score opportunities across IV, POP, RR/EV, theta, liquidity.
  - Primary structures: debit spreads, credit spreads, iron condors, calendars.
  - Selection emphasizes balanced scoring and controlled drawdown.

### Risk Management Principles
- **Per‑trade risk caps** (defined in each strategy).
- **Portfolio heat limits** (avoid over‑exposure).
- **Time‑based exits** to avoid end‑of‑day risk.
- **Liquidity filters** (min OI/volume, max spread).

### Monitoring & Logging
- Structured logs (`[ENTRY]`, `[EXIT]`, `[REJECTED]`, `[POSITION]`, `[METRICS]`)
- Central monitor via `openalgo/scripts/monitor_trades.py`
- Broker positionbook is used to reconcile live positions.

## 🛡️ System Audit & Performance (Feb 2026)

### Audit Findings
- **High Correlation:** Strategies `SuperTrendVWAP`, `TrendPullback`, and `ORB` showed 100% correlation in recent logs. This poses a risk of simultaneous drawdowns.
  - **Action:** Recommend consolidating capital into `SuperTrendVWAP` (Highest Calmar Ratio: ~17.7k) and investigating/diversifying the other two logic.
- **Equity Curve Stress Test:**
  - **Worst Day:** 2026-01-19.
  - **Worst Strategy:** `TrendPullback` (relative to potential).
  - The system has shown resilience but the lack of diversity in signals is a concern.

### Infrastructure Upgrades
- **Batch Data Fetching:** Implemented `get_batch_quotes` in Dhan sandbox and `APIClient` to reduce latency when tracking multiple instruments.
- **Caching:** Added caching to `get_instruments` to minimize API load.
- **Adaptive Sizing:** Updated `PositionManager` to include `calculate_adaptive_quantity`, allowing position sizing based on ATR volatility (Target Risk / ATR).

## 🚀 Ahead Roadmap

Based on the audit, the following areas are prioritized for the next iteration:

1.  **Gamma Scalping on Earnings:** Explore strategies that exploit high IV environments around earnings releases, hedging delta while capturing gamma.
2.  **Mean Reversion on High IV Rank:** Develop a counter-trend strategy specifically for instruments with IV Rank > 80, fading extreme moves.
3.  **Volume Profile POC Bounce:** Implement a strategy trading off the Point of Control (POC) from the previous day's Volume Profile, aiming for mean reversion or support/resistance tests.

## 🛡️ System Audit & Performance (Feb 2026)

### Audit Findings
- **High Correlation:** Strategies `SuperTrendVWAP`, `TrendPullback`, and `ORB` showed 100% correlation in recent logs. This poses a risk of simultaneous drawdowns.
  - **Action:** Recommend consolidating capital into `SuperTrendVWAP` (Highest Calmar Ratio: ~17.7k) and investigating/diversifying the other two logic.
- **Equity Curve Stress Test:**
  - **Worst Day:** 2026-01-19.
  - **Worst Strategy:** `TrendPullback` (relative to potential).
  - The system has shown resilience but the lack of diversity in signals is a concern.

### Infrastructure Upgrades
- **Caching:** Implemented file-based caching for historical data in the Dhan Sandbox API to reduce latency and API load.
- **Adaptive Sizing:** Updated `PositionManager` to include `calculate_adaptive_quantity_monthly_atr`, allowing position sizing based on Monthly ATR for robust risk management.

## 🚀 Ahead Roadmap

Based on the audit, the following areas are prioritized for the next iteration:

1.  **Volume Profile & VIX-Adjusted VWAP:** Enhance execution logic by integrating Volume Profile Point of Control (POC) and adjusting VWAP bands based on VIX.
2.  **Sector Rotation with Relative Strength:** Develop a strategy to detect regime changes by tracking Relative Strength of sectors vs Nifty.
3.  **Gamma Scalping on Earnings:** Explore high variance plays during earnings season to capture gamma moves.
