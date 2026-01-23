# Iron Condor Strategy Test - NIFTY Historical Data

## 🎯 Test Configuration

**Strategy**: Iron Condor (9-20 DTE)
- **Min Days to Expiry**: 9
- **Max Days to Expiry**: 20
- **Call Spread Width**: 200 points
- **Put Spread Width**: 200 points
- **Call Short Strike Offset**: 200 points OTM
- **Put Short Strike Offset**: 200 points OTM
- **IV Percentile Range**: 30-70%

## 📋 What Was Created

### 1. Iron Condor Strategy (`packages/core/strategies/iron_condor.py`)

A complete Iron Condor options strategy that:
- Constructs 4-leg spreads (call spread + put spread)
- Selects strikes based on ATM and offsets
- Filters by IV percentile and DTE
- Calculates max profit/loss
- Generates signals with proper risk-reward

### 2. Test Script (`scripts/test_iron_condor.py`)

Comprehensive backtest script that:
- Tests Iron Condor on NIFTY historical data
- Uses 9-20 DTE parameters
- Provides detailed performance metrics
- Shows sample trades
- Gives recommendations

## 🚀 How to Run

### Step 1: Install Dependencies

```bash
cd /Users/mac/AITRAPP

# Create virtual environment (if not exists)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Run the Test

```bash
# Activate virtual environment
source venv/bin/activate

# Run Iron Condor backtest
python scripts/test_iron_condor.py
```

### Alternative: Via API

```bash
# Start API server first
make paper

# In another terminal, run backtest via API
curl -X POST http://localhost:8000/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "NIFTY",
    "start_date": "2025-08-15",
    "end_date": "2025-11-10",
    "initial_capital": 1000000,
    "strategy": "IronCondor"
  }' | jq
```

## 📊 Expected Output

The test will show:

```
🧪 IRON CONDOR BACKTEST - NIFTY Historical Data
======================================================================

📋 Strategy Parameters:
   Call Spread Width: 200 points
   Put Spread Width: 200 points
   Call Short Strike Offset: 200 points
   Put Short Strike Offset: 200 points
   Days to Expiry: 9 - 20
   IV Percentile Range: 30 - 70

📅 Backtest Period:
   Start: 2025-08-15
   End: 2025-11-10
   Initial Capital: ₹1,000,000

🚀 Starting backtest...

======================================================================
📊 BACKTEST RESULTS
======================================================================

💰 Capital & Returns:
   Initial Capital:     ₹1,000,000.00
   Final Capital:       ₹...
   Total Return:        ₹...
   Total Return %:      ...%
   Max Drawdown:        ...%

📈 Trade Statistics:
   Total Trades:        ...
   Winning Trades:      ...
   Losing Trades:       ...
   Win Rate:            ...%

💵 P&L Analysis:
   Average Win:         ₹...
   Average Loss:        ₹...
   Profit Factor:       ...
   Largest Win:         ₹...
   Largest Loss:        ₹...

📊 Strategy Performance:
   Signals Generated:  ...
   Execution Rate:     ...%

======================================================================
✅/❌ Performance Assessment
======================================================================
```

## 🔧 Customizing Parameters

Edit the parameters in `scripts/test_iron_condor.py`:

```python
iron_condor_params = {
    "call_spread_width": 200,           # Change spread width
    "put_spread_width": 200,
    "call_short_strike_offset": 200,    # Change strike offsets
    "put_short_strike_offset": 200,
    "max_dte": 20,                      # Change DTE range
    "min_dte": 9,
    "target_profit_pct": 50,            # Profit target
    "max_loss_pct": 200,                # Loss limit
    "iv_percentile_min": 30,            # IV filter
    "iv_percentile_max": 70,
    "max_positions": 2
}
```

## 📈 Understanding Iron Condor

### Structure

An Iron Condor consists of:
1. **Short Call Spread**: Sell lower strike call, buy higher strike call
2. **Short Put Spread**: Sell higher strike put, buy lower strike put

### Profit Zone

- Maximum profit when underlying stays between the two short strikes
- Profit = Net credit received
- Maximum loss = Width of wider spread - Net credit

### Example

If NIFTY is at 25,000:
- **Call Spread**: Sell 25,200 CE, Buy 25,400 CE
- **Put Spread**: Sell 24,800 PE, Buy 24,600 PE
- **Profit Zone**: 24,800 to 25,200
- **Max Loss**: If NIFTY moves beyond either spread

## ⚙️ Strategy Logic

The strategy:
1. **Filters by DTE**: Only trades 9-20 days to expiry
2. **Filters by IV**: Only when IV percentile is 30-70%
3. **Selects Strikes**: Based on ATM ± offset
4. **Calculates Credit**: Estimates net credit received
5. **Sets Targets**: 50% profit target, 200% loss stop
6. **Manages Risk**: Position sizing based on max loss

## 📊 What to Look For

### Good Results
- ✅ Positive total return
- ✅ Win rate > 60%
- ✅ Profit factor > 1.5
- ✅ Max drawdown < 10%
- ✅ Consistent monthly performance

### Warning Signs
- ⚠️ Very few trades (too selective)
- ⚠️ Low win rate (< 50%)
- ⚠️ High drawdown (> 15%)
- ⚠️ Negative profit factor

## 🔍 Analysis Tips

1. **Review Trade Distribution**: Are trades evenly distributed or clustered?
2. **Check Exit Reasons**: Which exits are most common?
3. **Monthly Performance**: Are there better/worse months?
4. **Strike Selection**: Are selected strikes appropriate?
5. **IV Impact**: How does IV affect performance?

## 🎯 Next Steps After Testing

1. **Parameter Optimization**: Test different strike offsets and DTE ranges
2. **Walk-Forward**: Test on different date ranges
3. **Sensitivity Analysis**: See how results change with parameters
4. **Paper Trading**: If results look good, test in paper mode
5. **Live Trading**: Only after thorough validation

## 📝 Notes

- The current implementation uses estimated option prices
- For more accurate results, enhance with actual bid/ask from historical data
- Consider adding Greeks (Delta, Theta, Vega) for better analysis
- Monitor assignment risk (though rare in India with cash settlement)

## 🐛 Troubleshooting

### "No signals generated"
- Check if IV percentile is in range
- Verify date range has trading days
- Check if strikes are available in data

### "Very few trades"
- Widen IV percentile range
- Adjust strike offsets
- Extend DTE range

### "All losses"
- Review exit rules
- Check if credit estimates are realistic
- Consider tighter profit targets

---

**Ready to test! Run `python scripts/test_iron_condor.py` after installing dependencies.**

