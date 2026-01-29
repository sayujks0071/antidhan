# OpenAlgo Daily Prep & Backtesting Guide

This guide details the daily workflow for ensuring OpenAlgo is ready for trading, verifying symbols, and ranking strategies.

## 1. Daily Preparation

The `daily_startup.py` script is the main entry point for the trading day. It ensures the OpenAlgo repository is present and then executes the preparation workflow.

### Usage
```bash
./daily_startup.py
```

### What it does:
1.  **Repository Check**: Checks for `openalgo/` directory. If missing, clones it from the repository.
2.  **Daily Prep**: Launches `openalgo/scripts/daily_prep.py` which:
    *   **Environment Check**: Verifies `OPENALGO_APIKEY` and repo structure.
    *   **Purge Stale State**: Deletes previous day's:
        *   Strategy state files (`openalgo/strategies/state/*.json`)
        *   Cached instruments (`openalgo/data/instruments.csv`)
        *   Session files (if any)
    *   **Authentication Check**: Verifies connectivity to Broker (Kite/Dhan).
    *   **Fetch Instruments**: Downloads the latest instrument list from the broker (or generates a mock list if API is unavailable).
    *   **Symbol Validation**: Resolves all strategies in `active_strategies.json` to valid, tradable symbols for *today*.

### Output
The script outputs a validation table. If any strategy has an invalid symbol (e.g., expired option, missing future), the script **exits with an error**, preventing trading.

```
--- SYMBOL VALIDATION REPORT ---
STRATEGY             | TYPE     | INPUT           | RESOLVED                  | STATUS
------------------------------------------------------------------------------------------
ORB_NIFTY            | EQUITY   | NIFTY           | NIFTY                     | ✅ Valid
ATM_OPT_NIFTY        | OPT      | NIFTY           | Expiry: 2026-01-31        | ✅ Valid
MCX_SILVER           | FUT      | SILVER          | SILVERMIC23NOVFUT         | ✅ Valid
```

## 2. Strategy Configuration

Strategies are defined in `openalgo/strategies/active_strategies.json`.

### Example Config
```json
{
    "ORB_NIFTY": {
        "strategy": "orb_strategy",
        "underlying": "NIFTY",
        "type": "EQUITY",
        "exchange": "NSE",
        "params": { "quantity": 50 }
    },
    "MCX_SILVER": {
        "strategy": "mcx_commodity_momentum_strategy",
        "underlying": "SILVER",
        "type": "FUT",
        "exchange": "MCX",
        "params": { "quantity": 1 }
    }
}
```

## 3. Symbol Resolver Logic

The `SymbolResolver` (`openalgo/strategies/utils/symbol_resolver.py`) handles dynamic symbol selection.

*   **Equity**: Verifies existence in master list.
*   **Futures (NSE/MCX)**:
    *   Selects the nearest expiry.
    *   **MCX Specific**: Prefers **MINI** contracts (containing 'M' or 'MINI') if available. Fallback to standard if not.
*   **Options**:
    *   Filters by Underlying, Type (CE/PE).
    *   Selects expiry based on preference (WEEKLY/MONTHLY).
    *   Validates that contracts exist for the target date.

## 4. Daily Backtest & Ranking

To run a simulation backtest of all active strategies:

```bash
./openalgo/scripts/run_daily_backtest.py
```

This script:
1.  Loads `active_strategies.json`.
2.  Resolves symbols using the fresh instrument list.
3.  **Real Backtest**: Runs the actual strategy logic (e.g. `ORBStrategy.calculate_signals`) against generated/historical data.
4.  **Fine-Tuning**: Automatically runs a grid search optimization for supported strategies (e.g., finding optimal `minutes` for ORB).
5.  Generates a Leaderboard (console table + `leaderboard.json`).

## 5. Troubleshooting

*   **API Connection Failed**: Ensure the local OpenAlgo server (port 5001/5002) is running.
*   **Invalid Symbol**:
    *   Check `instruments.csv` in `openalgo/data`.
    *   Verify the contract exists (e.g., is today a holiday? did expiry happen yesterday?).
    *   Update `active_strategies.json` if the underlying name changed.
*   **Login Issues**: Run `openalgo/scripts/authentication_health_check.py` manually for details.
