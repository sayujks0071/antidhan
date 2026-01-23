# Daily Trading System Review & Improvement Brief

**Date:** 2026-01-22
**Reviewer:** Jules (Expert Trading Systems Engineer)

## 1. Top 5 Findings (Prioritized)

1.  **Hardcoded Absolute Paths (Critical)**: `monitor_trades.py` and `aitrapp_integration.py` contained user-specific paths (`/Users/mac/dyad-apps/...`), breaking deployment on other environments.
2.  **Brittle Monitoring Logic (High)**: The monitoring script relies on process name parsing (`ps` output) and specific log file patterns, which is prone to failure if strategy naming conventions change.
3.  **Strategy Quality (High)**: The `ORBStrategy` generates frequent signals with a high Stop Loss (SL) rate (~50% in logs). It lacks a trend filter, entering trades purely on breakouts even against the major trend.
4.  **Environment/Secrets Hygiene (Medium)**: API keys and configuration paths were hardcoded or loosely handled. `monitor_trades.py` contained hardcoded broker URLs (`http://127.0.0.1:5001`), limiting flexibility for the dual-broker setup.
5.  **Data Robustness (Medium)**: Strategies rely on 5-second bars (`bars_5s`). While good for execution, longer-term trend context is missing or requires aggregation, leading to noise.

## 2. Files Changed

1.  `openalgo/scripts/monitor_trades.py`: Refactored to use relative paths and removed hardcoded user directories.
2.  `openalgo/strategies/utils/aitrapp_integration.py`: Refactored to dynamically locate the `AITRAPP` repository.
3.  `AITRAPP/AITRAPP/packages/core/strategies/orb_trend.py`: **New Strategy Module** implementing ORB with an EMA Trend Filter.

## 3. Implemented Improvements

### A. System Portability Fixes
**File:** `openalgo/scripts/monitor_trades.py`
- Replaced `Path("/Users/mac/...")` with `Path(__file__).resolve().parent.parent / ...`
- This ensures the monitoring script works from any directory structure as long as the internal `openalgo` structure is preserved.

### B. Strategy Enhancement: ORB Trend Filter
**File:** `AITRAPP/AITRAPP/packages/core/strategies/orb_trend.py`
- **New Strategy**: `ORBTrendStrategy` extends `ORBStrategy`.
- **Logic**: Adds an Exponential Moving Average (EMA) filter.
    - **Long Condition**: Breakout + Price > EMA(100)
    - **Short Condition**: Breakdown + Price < EMA(100)
- **Rationale**: Based on trade logs, many SL hits occurred during chop or counter-trend moves. This filter enforces trading only in the direction of the momentum.

### C. AITRAPP Integration
**File:** `openalgo/strategies/utils/aitrapp_integration.py`
- Replaced hardcoded search paths with relative path traversal to robustly find the backtesting engine.

## 4. Test & Verification Steps

1.  **Verify Path Resolution**:
    ```bash
    # Should run without "File not found" errors for configs (though may report no processes running)
    python3 openalgo/scripts/monitor_trades.py
    ```
2.  **Verify Strategy Syntax**:
    ```bash
    python3 -m py_compile AITRAPP/AITRAPP/packages/core/strategies/orb_trend.py
    ```
3.  **Backtest/Dry Run**:
    - Update `strategy_configs.json` to use `ORBTrendStrategy`.
    - Run the backtest script (existing workflow) to compare `ORBTrendStrategy` vs `ORBStrategy`.

## 5. Risk Notes

-   **Process Monitoring**: The `monitor_trades.py` script still relies on `psutil` finding python processes with specific command lines. If the deployment method changes (e.g., to Docker containers without exposing PIDs, or different entry points), this monitoring will fail.
-   **EMA Data Requirement**: The new `ORBTrendStrategy` requires at least `ema_period` bars of data. On a fresh restart, it will not trade until enough 5s bars are collected (e.g., 100 bars = ~8 minutes). This is a safe fallback but delays startup entries.
-   **Broker URLs**: `monitor_trades.py` still defaults to `http://127.0.0.1:5001`. If the Kite instance is on a different port or host, this needs to be configurable via env vars (added `BASE_URL` var but defaulting to localhost).
