# Backtest Engine Setup and Usage

This directory contains the backtest engine integration with AITRAPP to test and rank OpenAlgo strategies.

## Prerequisites

1. **AITRAPP Repository**: Ensure AITRAPP is cloned and available
   - Location: `/Users/mac/dyad-apps/AITRAPP/AITRAPP` (or update path in `utils/aitrapp_integration.py`)

2. **Python Dependencies**: Install required packages
   ```bash
   pip install pyyaml structlog pandas numpy scipy
   ```

3. **Historical Data**: Ensure AITRAPP has historical data
   - Location: `AITRAPP/AITRAPP/docs/NSE OPINONS DATA/`
   - Should contain CSV files for NIFTY and BANKNIFTY options

## Quick Start

### 1. Test Setup

```bash
cd openalgo/strategies
python3 scripts/test_backtest_setup.py
```

This will verify:
- AITRAPP integration
- API mock module
- Strategy adapters
- Historical data availability

### 2. Run Backtest

```bash
# Test all available strategies
python3 scripts/run_backtest_ranking.py \
    --symbol NIFTY \
    --start-date 2025-08-15 \
    --end-date 2025-11-10 \
    --capital 1000000

# Test specific strategies
python3 scripts/run_backtest_ranking.py \
    --strategies nifty_greeks_enhanced \
    --start-date 2025-08-15 \
    --end-date 2025-11-10
```

### 3. View Results

Results are saved to:
- `backtest_results/backtest_results.json` - Detailed results
- `backtest_results/strategy_rankings.csv` - Rankings table
- `backtest_results/backtest_results.csv` - All results

## Architecture

### Components

1. **AITRAPP Integration** (`utils/aitrapp_integration.py`)
   - Sets up Python path to AITRAPP
   - Imports AITRAPP modules (BacktestEngine, HistoricalDataLoader, etc.)

2. **OpenAlgo API Mock** (`utils/openalgo_mock.py`)
   - Simulates OpenAlgo API endpoints using historical data
   - Converts AITRAPP data structures to OpenAlgo API format

3. **Strategy Adapters** (`adapters/*.py`)
   - Bridge OpenAlgo strategies to AITRAPP Strategy interface
   - Extract entry logic and convert to signals

4. **Backtest Runner** (`scripts/run_backtest_ranking.py`)
   - Runs backtests on all strategies
   - Ranks strategies by composite score
   - Generates reports

## Ranking Metrics

Strategies are ranked by a composite score using:

- **Total Return %** (weight: 30%)
- **Win Rate** (weight: 20%)
- **Profit Factor** (weight: 25%)
- **Max Drawdown %** (inverse, weight: 15%)
- **Total Trades** (normalized, weight: 10%)

## Available Strategies

Currently implemented adapters:
- `nifty_greeks_enhanced` - NIFTY Greeks Enhanced strategy
- `nifty_multistrike_momentum` - NIFTY Multi-Strike Momentum strategy

More adapters can be added by creating new files in `adapters/` directory.

## Troubleshooting

### Missing Dependencies

If you see `ModuleNotFoundError`:
```bash
pip install pyyaml structlog pandas numpy scipy
```

### AITRAPP Path Not Found

Update the path in `utils/aitrapp_integration.py`:
```python
possible_paths = [
    Path("/your/path/to/AITRAPP/AITRAPP"),
    ...
]
```

### Historical Data Not Found

Ensure CSV files exist in:
```
AITRAPP/AITRAPP/docs/NSE OPINONS DATA/
```

Files should be named:
- `OPTIDX_NIFTY_CE_*.csv`
- `OPTIDX_NIFTY_PE_*.csv`
- `OPTIDX_BANKNIFTY_CE_*.csv`
- `OPTIDX_BANKNIFTY_PE_*.csv`

## Configuration

Edit `config/backtest_config.py` to customize:
- Default date range
- Initial capital
- Ranking weights
- Output paths

## Notes

- Backtests use historical data, so results may differ from live trading
- API mock provides simplified Greeks calculations
- Some strategies may need adapter updates for full functionality
- Results are saved automatically after each run
