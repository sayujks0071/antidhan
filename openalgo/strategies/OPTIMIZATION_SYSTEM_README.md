# Strategy Parameter Optimization System

## Overview

A comprehensive parameter optimization framework for MCX commodity trading strategies. The system uses grid search and Bayesian optimization to systematically test parameter combinations and identify optimal configurations.

## Components

### 1. Parameter Space Definition (`utils/parameter_space.py`)
- Defines parameter ranges for each strategy
- Provides grid search and continuous ranges for Bayesian optimization
- Includes normalization utilities for weights

### 2. Strategy Parameter Injector (`utils/strategy_param_injector.py`)
- Dynamically loads strategy modules
- Injects test parameters into strategies
- Handles weight normalization and parameter dependencies

### 3. Optimization Engine (`utils/optimization_engine.py`)
- **GridSearchOptimizer**: Exhaustive search of key parameters
- **BayesianOptimizer**: Intelligent search using scikit-optimize (falls back to random search if unavailable)
- Calculates composite scores for ranking strategies

### 4. Optimization Runner (`scripts/optimize_strategies.py`)
- CLI tool to run optimization workflows
- Supports grid search, Bayesian optimization, or hybrid approach
- Generates comprehensive reports and saves best parameters

## Usage

### Basic Usage

```bash
# Set API key
export OPENALGO_APIKEY="your_api_key_here"

# Optimize all strategies with hybrid method
cd openalgo/strategies
python3 scripts/optimize_strategies.py --strategies all --method hybrid

# Optimize specific strategy
python3 scripts/optimize_strategies.py --strategy natural_gas --method grid

# Custom date range
python3 scripts/optimize_strategies.py \
    --strategies natural_gas crude_oil \
    --start-date 2025-11-01 \
    --end-date 2026-01-27 \
    --method hybrid \
    --capital 1000000
```

### Command Line Options

- `--strategies`: Strategies to optimize (`natural_gas`, `crude_oil`, `all`)
- `--start-date`: Start date for backtesting (YYYY-MM-DD)
- `--end-date`: End date for backtesting (YYYY-MM-DD)
- `--method`: Optimization method (`grid`, `bayesian`, `hybrid`)
- `--capital`: Initial capital (default: 1000000)
- `--api-key`: OpenAlgo API key (or use OPENALGO_APIKEY env var)
- `--host`: OpenAlgo API host (default: http://127.0.0.1:5001)
- `--max-grid-combinations`: Limit grid search combinations
- `--bayesian-iterations`: Number of Bayesian iterations (default: 50)
- `--skip-grid`: Skip grid search, go straight to Bayesian

## Optimization Methods

### Grid Search
- Tests all combinations of key parameters
- Identifies promising parameter regions
- Best for initial exploration

### Bayesian Optimization
- Uses Gaussian Process or Random Forest to intelligently search
- Focuses search around promising regions
- More efficient for fine-tuning

### Hybrid (Recommended)
- Phase 1: Grid search on key parameters
- Phase 2: Bayesian optimization starting from best grid result
- Combines thoroughness with efficiency

## Composite Score

Strategies are ranked using a composite score:

```
composite_score = (
    return_score * 0.30 +
    win_rate_score * 0.20 +
    profit_factor_score * 0.25 +
    drawdown_score * 0.15 +
    trades_score * 0.10
)
```

Higher scores indicate better performance.

## Output Files

Results are saved to `optimization_results/`:

- `{strategy}_grid_search_{timestamp}.json`: All grid search results
- `{strategy}_bayesian_{timestamp}.json`: Bayesian optimization history
- `{strategy}_best_parameters.json`: Optimal parameters found
- `{strategy}_optimization_report.csv`: CSV report of all configurations

## Parameter Ranges

### Natural Gas Strategy
- Entry thresholds: BASE_ENTRY_THRESHOLD (50-70), MIN_ENTRY_THRESHOLD (45-55)
- Risk management: ATR_SL_MULTIPLIER (2.0-3.0), ATR_TP_MULTIPLIER (3.5-5.0)
- Timeframe weights: 15m (0.40-0.70), 5m (0.20-0.40), 1h (0.10-0.30)
- ADX adaptive factor: (0.3-0.5)

### Crude Oil Strategy
- Entry thresholds: BASE_ENTRY_THRESHOLD (50-65), MIN_ENTRY_THRESHOLD (45-50)
- Risk management: ATR_SL_MULTIPLIER (1.5-2.5), ATR_TP_MULTIPLIER (2.5-4.0)
- Timeframe weights: 15m (0.50-0.70), 5m (0.15-0.25), 1h (0.10-0.20)
- ADX adaptive factor: (0.30-0.40)

## Requirements

- Python 3.7+
- pandas, numpy
- scikit-optimize (optional, for Bayesian optimization)
- httpx (for API calls)

Install optional dependencies:
```bash
pip install scikit-optimize
```

## Notes

- The system handles parameter normalization automatically (weights sum to 1.0)
- Strategies must expose a `generate_signal()` function for backtesting
- API key must be set via environment variable or `--api-key` argument
- Grid search can generate many combinations - use `--max-grid-combinations` to limit
- Bayesian optimization requires scikit-optimize; otherwise falls back to random search

## Example Output

```
======================================================================
Optimizing: natural_gas_clawdbot
======================================================================

Phase 1: Grid Search - natural_gas_clawdbot
======================================================================
Testing 2160 parameter combinations...
Progress: 10/2160 combinations tested
...

Top 10 Configurations:
1. Score: 45.23 | Return: 12.5% | Win Rate: 58.3% | Trades: 24
2. Score: 43.87 | Return: 11.2% | Win Rate: 56.1% | Trades: 28
...

Phase 2: Bayesian Optimization - natural_gas_clawdbot
======================================================================
Best Parameters Found:
Composite Score: 47.89
Parameters: {
  "BASE_ENTRY_THRESHOLD": 62,
  "ATR_SL_MULTIPLIER": 2.3,
  ...
}
```

## Next Steps

After optimization:
1. Review best parameters in `optimization_results/{strategy}_best_parameters.json`
2. Update strategy files with optimal parameters
3. Validate on out-of-sample data
4. Deploy optimized strategies
