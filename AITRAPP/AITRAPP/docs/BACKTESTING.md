# Backtesting with Historical Data

AITRAPP includes a comprehensive backtesting engine that uses historical NSE options data to test strategies before live trading.

## 📊 Historical Data Files

The system includes historical options data for:
- **NIFTY** (CE and PE)
- **BANKNIFTY** (CE and PE)

**Location**: `docs/NSE OPINONS DATA/`

**Date Range**: August 12, 2025 to November 12, 2025

**Data Format**: CSV files with columns:
- Symbol, Date, Expiry, Option type, Strike Price
- OHLC data (Open, High, Low, Close, LTP, Settle Price)
- Volume (No. of contracts, Turnover, Premium Turnover)
- Open Interest (OI, Change in OI)
- Underlying Value

## 🚀 Quick Start

### Option 1: CLI Script

```bash
# Run backtest on NIFTY with all strategies
python scripts/run_backtest.py \
    --symbol NIFTY \
    --start-date 2025-08-15 \
    --end-date 2025-11-10 \
    --capital 1000000

# Test specific strategy
python scripts/run_backtest.py \
    --symbol BANKNIFTY \
    --start-date 2025-09-01 \
    --end-date 2025-10-31 \
    --strategy ORB \
    --capital 500000
```

### Option 2: API Endpoint

```bash
# Run backtest via API
curl -X POST http://localhost:8000/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "NIFTY",
    "start_date": "2025-08-15",
    "end_date": "2025-11-10",
    "initial_capital": 1000000,
    "strategy": "all"
  }' | jq
```

### Option 3: Python Code

```python
from datetime import datetime
from packages.core.backtest import BacktestEngine
from packages.core.strategies import ORBStrategy
from packages.core.config import app_config

# Initialize backtest engine
engine = BacktestEngine(
    initial_capital=1000000,
    data_dir="docs/NSE OPINONS DATA"
)

# Get strategy config
orb_config = app_config.get_strategy_by_name("ORB")
strategy = ORBStrategy("ORB", orb_config.params)

# Run backtest
results = engine.run_backtest(
    strategies=[strategy],
    symbol="NIFTY",
    start_date=datetime(2025, 8, 15),
    end_date=datetime(2025, 11, 10)
)

# Print results
print(f"Total Return: {results['total_return_pct']:.2f}%")
print(f"Win Rate: {results['win_rate']:.2f}%")
print(f"Total Trades: {results['total_trades']}")
```

## 📈 Understanding Results

### Performance Metrics

The backtest returns comprehensive metrics:

```json
{
  "initial_capital": 1000000,
  "final_capital": 1050000,
  "total_return": 50000,
  "total_return_pct": 5.0,
  "max_drawdown_pct": 2.5,
  "total_trades": 45,
  "wins": 28,
  "losses": 17,
  "win_rate": 62.22,
  "avg_win": 2500,
  "avg_loss": -1500,
  "profit_factor": 2.74,
  "largest_win": 8500,
  "largest_loss": -3200
}
```

### Key Metrics Explained

- **Total Return %**: Overall profit/loss as percentage
- **Max Drawdown %**: Largest peak-to-trough decline
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Ratio of gross profit to gross loss
- **Avg Win/Loss**: Average profit per winning/losing trade

### Interpreting Results

**Good Backtest Results**:
- ✅ Positive total return
- ✅ Win rate > 50%
- ✅ Profit factor > 1.5
- ✅ Max drawdown < 10%
- ✅ Consistent performance across date range

**Warning Signs**:
- ⚠️ High win rate but negative return (small wins, large losses)
- ⚠️ Very few trades (may be overfitting)
- ⚠️ Extreme drawdowns (>20%)
- ⚠️ Inconsistent performance (good months, bad months)

## 🔧 Advanced Usage

### Testing Specific Strikes

```python
from packages.core.backtest import BacktestEngine

engine = BacktestEngine(initial_capital=1000000)

# Test specific strikes
results = engine.run_backtest(
    strategies=[strategy],
    symbol="NIFTY",
    start_date=datetime(2025, 8, 15),
    end_date=datetime(2025, 11, 10),
    strikes=[24000, 24500, 25000, 25500, 26000]  # Specific strikes
)
```

### Analyzing Individual Trades

```python
# After running backtest
for trade in engine.closed_trades:
    print(f"Entry: {trade['entry_date']}, Exit: {trade['exit_date']}")
    print(f"Symbol: {trade['symbol']}, P&L: ₹{trade['pnl']:.2f}")
    print(f"Exit Reason: {trade['exit_reason']}")
    print()
```

### Daily P&L Analysis

```python
import pandas as pd

# Convert daily P&L to DataFrame
daily_pnl = pd.DataFrame([
    {"date": date, "pnl": pnl}
    for date, pnl in results['daily_pnl'].items()
])

# Plot equity curve
daily_pnl['cumulative'] = daily_pnl['pnl'].cumsum()
daily_pnl.plot(x='date', y='cumulative')
```

## 📊 Data Loading

### Load Historical Data Directly

```python
from packages.core.historical_data import HistoricalDataLoader

loader = HistoricalDataLoader(data_dir="docs/NSE OPINONS DATA")

# Load all NIFTY CE data
df = loader.load_file("NIFTY", "CE")

# Load specific date range
from datetime import datetime
df = loader.load_file(
    "NIFTY",
    "CE",
    start_date=datetime(2025, 9, 1),
    end_date=datetime(2025, 10, 31)
)

# Get options chain for a specific date
chain = loader.get_options_chain("NIFTY", datetime(2025, 9, 15))

# Get data for specific strike
strike_data = loader.get_strike_data("NIFTY", "CE", 25000)
```

### Get ATM Strikes

```python
# Get strikes around ATM for a date
strikes = loader.get_atm_strikes("NIFTY", datetime(2025, 9, 15), num_strikes=5)
print(f"ATM Strikes: {strikes}")
```

## ⚙️ Configuration

Backtesting uses the same risk and strategy configurations as live trading:

- **Risk Limits**: From `configs/app.yaml` → `risk` section
- **Strategy Parameters**: From `configs/app.yaml` → `strategies` section
- **Exit Rules**: From `configs/app.yaml` → `exits` section

Modify these before running backtests to test different parameter sets.

## 🎯 Best Practices

### 1. Walk-Forward Analysis

Don't just test on one date range. Test multiple periods:

```bash
# Test Q3 2025
python scripts/run_backtest.py --start-date 2025-08-15 --end-date 2025-09-30

# Test Q4 2025
python scripts/run_backtest.py --start-date 2025-10-01 --end-date 2025-11-10
```

### 2. Out-of-Sample Testing

- Use 70% of data for parameter optimization
- Test on remaining 30% (out-of-sample)
- If results differ significantly, strategy may be overfitted

### 3. Multiple Market Conditions

Test during:
- Trending markets
- Range-bound markets
- High volatility periods
- Low volatility periods

### 4. Sensitivity Analysis

Test how results change with parameter variations:

```python
# Test different risk percentages
for risk_pct in [0.3, 0.5, 0.7, 1.0]:
    # Modify config and run backtest
    # Compare results
```

## ⚠️ Limitations

### Current Limitations

1. **Simplified Execution**: Paper simulator uses static slippage
2. **No Bid-Ask Spread**: Historical data uses LTP, not bid/ask
3. **No Partial Fills**: Orders fill completely or not at all
4. **Static IV**: IV calculations are simplified (not Black-Scholes)
5. **No Market Impact**: Large orders don't affect price

### Future Enhancements

- [ ] Realistic slippage model based on volume
- [ ] Bid-ask spread simulation
- [ ] Partial fill simulation
- [ ] Proper IV calculation (Black-Scholes)
- [ ] Market impact modeling
- [ ] Multi-timeframe backtesting

## 📝 Example Workflow

### Complete Backtesting Workflow

```bash
# 1. Review historical data
ls -lh docs/NSE\ OPINONS\ DATA/

# 2. Run initial backtest
python scripts/run_backtest.py \
    --symbol NIFTY \
    --start-date 2025-08-15 \
    --end-date 2025-11-10 \
    --strategy all

# 3. Analyze results
# Review win rate, profit factor, drawdown

# 4. Tune parameters
# Edit configs/app.yaml
# Adjust strategy parameters, risk limits

# 5. Re-run backtest
python scripts/run_backtest.py ...

# 6. Compare results
# Document parameter changes and impact

# 7. Paper trade
# If backtest looks good, test in paper mode

# 8. Live trading (after 2+ weeks paper)
# Only if paper trading confirms backtest results
```

## 🔍 Troubleshooting

### Issue: "Historical data file not found"

**Solution**: Verify CSV files are in `docs/NSE OPINONS DATA/`

```bash
ls docs/NSE\ OPINONS\ DATA/
```

### Issue: "No data for date range"

**Solution**: Check available date range:

```python
from packages.core.historical_data import HistoricalDataLoader

loader = HistoricalDataLoader()
start, end = loader.get_date_range("NIFTY", "CE")
print(f"Available: {start} to {end}")
```

### Issue: "No signals generated"

**Solution**: 
- Check strategy is enabled in `configs/app.yaml`
- Verify date range has trading days
- Check strategy parameters (may be too restrictive)

### Issue: "Backtest takes too long"

**Solution**:
- Reduce date range
- Test fewer strikes
- Test one strategy at a time

## 📚 Additional Resources

- **Strategy Development**: See `docs/STRATEGIES.md` (if created)
- **Risk Management**: See `configs/app.yaml` → `risk` section
- **Performance Analysis**: Use pandas for detailed analysis

## 💡 Tips

1. **Start Small**: Test on 1-2 weeks of data first
2. **Document Everything**: Keep notes on parameter changes
3. **Compare Strategies**: Run same period with different strategies
4. **Look for Patterns**: Analyze which market conditions favor each strategy
5. **Be Skeptical**: If results seem too good, investigate for overfitting

---

**Remember**: Backtest results are historical and don't guarantee future performance. Always paper trade before going live!

