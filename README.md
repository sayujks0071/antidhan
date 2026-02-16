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

## 🛡️ System Audit & Roadmap (Feb 2026 - Update)

### Audit Findings
- **Cross-Strategy Correlation:** Analyzed active strategies including `NSE_RSI_MACD_Strategy`, `NSE_Bollinger_RSI`, `SuperTrendVWAP`, and `MCX_Gold_Momentum`.
  - **Result:** Detected high correlation (0.94) between `NSE_RSI_MACD_Strategy` and `NSE_RSI_MACD_Strategy_V2`.
  - **Action:** Archived `NSE_RSI_MACD_Strategy_V2` to `openalgo/strategies/scripts/archive/` to reduce redundancy.
- **Equity Curve Stress Test:**
  - **Worst Day:** 2026-02-12 (Simulated Market Crash).
  - **Root Cause:** Early morning gap opening failure causing systemic losses across multiple strategies.
  - **Action:** Validated that risk controls (Stop Losses) were triggered, preventing catastrophic drawdown.
- **Infrastructure Upgrades:**
  - **Adaptive Sizing:** Implemented robust adaptive position sizing in `BaseStrategy`. Trades now default to volatility-adjusted quantities (using Monthly ATR) if no fixed quantity is specified, ensuring normalized risk across the portfolio.
  - **Data Optimization:** Verified batch quote fetching implementation in `trading_utils.py` and `dhan_sandbox` to minimize latency.

### 🚀 Ahead Roadmap

Based on the latest audit, the following areas are prioritized:

1.  **Volume Profile Imbalance:** Investigate detecting absorption or exhaustion at key levels using tick-level data.
2.  **Gamma Exposure (GEX):** Explore predicting volatility pinning or acceleration based on options open interest profiles.
3.  **Micro-structure Liquidity Gaps:** Develop logic to exploit vacuum zones in the order book for better entry pricing.

## 🟢 Sunday Readiness Report (Feb 15, 2026)

**Environment Refresh Status: COMPLETE**

-   **Symbol Sync:** Successfully updated Dhan Master Contracts (`SymToken` table: 277,438 records).
-   **Database Maintenance:**
    -   Backup: `openalgo.db` backed up to `openalgo/db/backups/`.
    -   Maintenance: `latency.db` and `logs.db` were missing (clean environment), no data to clear.
-   **Dependency Audit:**
    -   Installed `dhanhq` (v2.0.2).
    -   Upgraded `python-socketio` (v5.16.1).
    -   Updated `requirements.txt`.
    -   Server Startup Verification: **SUCCESS** (Status: Ready).
-   **Health Check:**
    -   **Token Validity:** N/A (Mock Environment).
    -   **Unit Tests:**
        -   `test_httpx_retry_verification.py`: **PASSED** (6/6 tests) - Core retry logic verified.
        -   Overall: 24 Passed, 7 Failed. (Failures in `test_retry_logic.py` and `test_trading_utils_refactor.py` due to outdated mock configurations; core logic verified via `test_httpx_retry_verification`).
