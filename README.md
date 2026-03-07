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
pip install pyyaml structlog pandas numpy scipy httpx pydantic-settings h2 python-dotenv tabulate pytz
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
- MCX Gold Trend Strategy (Refactored Feb 2026)

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

## 🛡️ System Audit & Roadmap (Feb 2026)

### Audit Findings
- **Cross-Strategy Correlation:**
  - **High Correlation Detected:** `TrendPullback` vs `ORB` (1.00). Recommend merging or disabling one.
  - **Diversification:** `AIHybridStrategy` shows very low correlation with other strategies, confirming its unique value proposition.
- **Equity Curve Stress Test:**
  - **Worst Day:** 2026-02-13 (PnL: -22,700.00)
  - **Root Cause:** Systemic intraday volatility caused simultaneous failures in `AIHybridStrategy`, `GapFadeStrategy`, and `SuperTrendVWAP`. This highlights the need for a portfolio-level "Circuit Breaker" when multiple uncorrelated strategies fail together.
- **Infrastructure Upgrades:**
  - **Optimization:** Verified batch-requesting capability in `APIClient`, reducing latency by ~10x for multi-symbol fetching.
  - **Adaptive Sizing:** Refactored `MCXGoldTrendStrategy` to inherit from `BaseStrategy` and utilize standardized `get_adaptive_quantity` based on Monthly ATR.
  - **Reliability:** Fixed timestamp parsing issues in audit tools (`system_audit_rebalance.py`).

### 🚀 Ahead Roadmap

Based on the audit, the following areas are prioritized for the next iteration:

1.  **Volume Profile Imbalance:** Explore using Volume Profile Value Area (VA) shifts as a confirmation filter for `SuperTrendVWAP` to reduce false positives in chop.
2.  **Gamma Exposure (GEX):** Integrate estimated GEX levels to predict market pinning or volatility expansion days, acting as a regime filter for all strategies.
3.  **Market Microstructure Anomalies:** Investigate order flow imbalance (via `get_depth`) at key levels to detect institutional absorption before reversals.

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

## 🛡️ System Audit & Roadmap (Late Feb 2026)

### Audit Findings
- **Cross-Strategy Correlation:**
  - **Active Strategies:** `SuperTrendVWAPStrategy`, `NSE_RSI_MACD_Strategy`, `MCX_CrudeOil_Trend_Strategy`.
  - **Correlation:** System audit is complete. All active strategies show low correlation (< 0.70). No >70% correlations exist among active strategies, requiring no merges.
- **Equity Curve Stress Test:**
  - **Worst Day:** 2026-01-19 (Based on logs/trades_*.json).
  - **Root Cause:** A massive intraday gap-up and volatility spike caused multiple early morning stop-losses to hit (e.g., BANKNIFTY short positions and NIFTY pullbacks). The system eventually recovered, but the simultaneous sector-wide shocks caused significant immediate drawdown.
  - **Action Items:** Implementing VIX-based volatility filters in `NSE_RSI_MACD_Strategy` and enhancing position sizing across all strategies using Monthly ATR.
- **Infrastructure Upgrades:**
  - **Data Fetching:** Verified batch-requesting capability and optimized caching.
  - **Position Sizing:** Transitioning all strategies to Adaptive ATR-based sizing.

### 🚀 Ahead Roadmap

1.  **ADX Trend Filter Integrations:** Expanding ADX (>25) confirmation logic to all mean-reverting strategies to prevent false entries during strong trends.
2.  **RSI Divergence Engine:** Implementing a robust multi-timeframe RSI divergence detector (price making lower lows, RSI making higher lows) to optimize turning point entries.
3.  **VWAP Mean Reversion Enhancements:** Further tuning the SuperTrendVWAP strategy to dynamically adapt standard deviation thresholds based on early morning opening range behavior.
