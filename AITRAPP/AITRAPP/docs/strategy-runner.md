# Strategy Runner Guide

This project includes a canonical runner for executing trading strategies in Backtest, Paper, and Live modes.

## Entry Point

The main entry point is `packages/core/runner.py`. You can run it as a module:

```bash
python -m packages.core.runner <command> [options]
```

## Backtest Mode

Run a strategy against historical data.

### Command

```bash
python -m packages.core.runner backtest \
  --strategy ORB \
  --symbol NIFTY \
  --start-date 2025-08-15 \
  --end-date 2025-08-18 \
  --data-dir tests/fixtures \
  --capital 1000000
```

### Options

*   `--strategy`: Strategy name (e.g., `ORB`, `TrendPullback`, `OptionsRanker`).
*   `--symbol`: `NIFTY` or `BANKNIFTY`.
*   `--start-date`: Start date (YYYY-MM-DD).
*   `--end-date`: End date (YYYY-MM-DD).
*   `--data-dir`: Directory containing historical CSV files (optional, defaults to `docs/NSE OPINONS DATA` or falls back to `tests/fixtures`).
*   `--capital`: Initial capital.

### Wrapper Script

You can also use the wrapper script:

```bash
python scripts/run_backtest.py --strategy ORB --data-dir tests/fixtures
```

## Paper-Local Mode

Run a strategy in a local simulation loop (in-process, no API server required). This simulates market data and execution.

### Command

```bash
python -m packages.core.runner paper-local \
  --strategy ORB \
  --symbol NIFTY \
  --minutes 10
```

### Options

*   `--minutes`: Duration of the simulation in minutes.

## Live Mode (GATED)

**WARNING**: Live mode connects to the real broker and places real orders.

It is gated by environment variables. To run:

```bash
export TRADING_MODE=live
export I_UNDERSTAND_LIVE_TRADING=true
python -m packages.core.runner live --strategy ORB
```

Without these flags, the runner will exit with an error.

## Adding Strategies

To add a new strategy, implement the `Strategy` interface in `packages/core/strategies/base.py` and register it in `packages/core/runner.py`'s `_load_strategies` method.

## Data

Backtesting requires historical options data in CSV format.
Default location: `docs/NSE OPINONS DATA/`
Fallback/Test location: `tests/fixtures/`

The fixture data allows you to verify the runner logic without needing the full historical dataset.
