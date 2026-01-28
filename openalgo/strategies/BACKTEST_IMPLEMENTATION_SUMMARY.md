# MCX Strategy Backtesting Implementation Summary

## Overview

Successfully created two optimized MCX commodity strategies (Natural Gas Mini and Crude Oil Mini) along with a comprehensive backtesting framework for evaluating their performance.

## Created Files

### 1. Strategies

#### Natural Gas Clawdbot Strategy
**File**: `scripts/natural_gas_clawdbot_strategy.py`

**Features**:
- Volatility-focused parameters optimized for Natural Gas (high volatility commodity)
- ATR-based stop loss: 2.5x ATR (wider stops for volatile instrument)
- Take profit: 4.0x ATR
- Entry confidence threshold: 60 (higher for volatile instruments)
- Multi-timeframe analysis (5m: 30%, 15m: 50%, 1h: 20%)
- Seasonality awareness (winter months get 10% boost to signals)
- Advanced indicators: RSI, MACD, ADX, Bollinger Bands, EMA crossovers, VWAP, Volume Ratio
- Regime detection (Trending vs Ranging)
- Dynamic entry thresholds based on ADX
- Clawdbot AI integration for market context

**Symbol**: `NATURALGAS24FEB26FUT`

#### Crude Oil Enhanced Strategy
**File**: `scripts/crude_oil_enhanced_strategy.py`

**Features**:
- Enhanced version with improved entry logic
- ATR-based stop loss: 1.8x ATR
- Take profit: 3.0x ATR
- Entry threshold: 58
- Multi-timeframe analysis (5m: 20%, 15m: 60%, 1h: 20%) - higher weight on primary timeframe
- Enhanced MACD weight (30% in trending markets)
- Improved EMA cross signals
- Better correlation awareness with Natural Gas (0.72 correlation)
- Extended trading hours awareness

**Symbol**: `CRUDEOIL19FEB26FUT`

### 2. Backtesting Framework

#### Simple Backtest Engine
**File**: `utils/simple_backtest_engine.py`

**Components**:
- `SimpleBacktestEngine`: Main backtest engine class
- `Trade`: Dataclass for tracking individual trades
- `Position`: Dataclass for tracking open positions

**Features**:
- Historical data loading from OpenAlgo API
- Position tracking with SL/TP management
- P&L calculation with slippage and transaction costs
- Performance metrics calculation:
  - Total return (%)
  - Win rate (%)
  - Profit factor
  - Max drawdown (%)
  - Average win/loss
  - Largest win/loss
  - Sharpe ratio
- Equity curve tracking
- Realistic cost modeling (5 bps slippage + 3 bps transaction costs)

#### Backtest Runner Script
**File**: `scripts/run_mcx_backtest.py`

**Features**:
- Command-line interface for running backtests
- Supports both Natural Gas and Crude Oil strategies
- Configurable date range (default: last 60 days)
- Generates CSV and JSON reports
- Comparison table showing both strategies side-by-side
- Composite scoring for strategy ranking

## Usage

### Running Backtests

```bash
cd openalgo/strategies

# Test both strategies (last 60 days)
python3 scripts/run_mcx_backtest.py --strategy both

# Test specific strategy
python3 scripts/run_mcx_backtest.py --strategy natural_gas
python3 scripts/run_mcx_backtest.py --strategy crude_oil

# Custom date range
python3 scripts/run_mcx_backtest.py \
    --strategy both \
    --start-date 2025-11-28 \
    --end-date 2026-01-27 \
    --capital 1000000

# With custom API key
OPENALGO_APIKEY="your_key" python3 scripts/run_mcx_backtest.py --strategy both
```

### Output Files

Results are saved to `backtest_results/` directory:
- `mcx_backtest_results.json`: Detailed results in JSON format
- `mcx_backtest_comparison.csv`: Comparison table in CSV format

## Strategy Comparison Metrics

The backtest framework compares strategies using a composite score:

- **Total Return %** (weight: 30%)
- **Win Rate %** (weight: 20%)
- **Profit Factor** (weight: 25%)
- **Max Drawdown %** (weight: 15%, inverse - lower is better)
- **Sharpe Ratio** (weight: 10%)

## Technical Details

### Risk Management

Both strategies use ATR-based risk management:
- Stop Loss: Calculated as entry_price ± (ATR_MULTIPLIER × ATR)
- Take Profit: Calculated as entry_price ± (ATR_MULTIPLIER × ATR)
- Position sizing: 1 lot per trade (configurable)

### Cost Modeling

Realistic cost assumptions:
- Slippage: 5 basis points per side
- Transaction costs: 3 basis points per side
- Total friction: 8 basis points per round trip

### Data Requirements

- Minimum bars: 50 (for indicator calculations)
- Data interval: 15 minutes (default, configurable)
- Required columns: open, high, low, close, volume

## Notes

1. **API Key**: Ensure `OPENALGO_APIKEY` environment variable is set or pass via `--api-key` argument
2. **Data Availability**: Backtests require historical data from OpenAlgo API. Ensure API is running and accessible.
3. **Performance**: Backtests may take several minutes for 60 days of 15-minute data
4. **Symbol Rollover**: Strategies use current active contracts. Update symbols when contracts expire.

## Next Steps

1. Run backtests with sufficient historical data
2. Analyze results and compare strategy performance
3. Optimize parameters based on backtest results
4. Deploy best-performing strategy for live trading

## Files Structure

```
openalgo/strategies/
├── scripts/
│   ├── natural_gas_clawdbot_strategy.py
│   ├── crude_oil_enhanced_strategy.py
│   └── run_mcx_backtest.py
├── utils/
│   └── simple_backtest_engine.py
└── backtest_results/
    ├── mcx_backtest_results.json
    └── mcx_backtest_comparison.csv
```

## Implementation Status

✅ Natural Gas strategy created
✅ Crude Oil enhanced strategy created
✅ Backtesting framework implemented
✅ Backtest runner script created
✅ Comparison reporting implemented
✅ Documentation completed

All components are ready for use. Run backtests with appropriate API credentials and historical data availability.
