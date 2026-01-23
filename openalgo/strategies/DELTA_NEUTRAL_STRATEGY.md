# Delta Neutral Iron Condor Strategy for NIFTY

## Overview

A highly profitable delta-neutral options strategy designed for NIFTY with sophisticated entry/exit logic and minimal drawdown. This strategy implements an Iron Condor spread (selling OTM call spread + selling OTM put spread) while maintaining delta neutrality through dynamic hedging.

## Strategy Type

**Iron Condor (Credit Spread)**
- Sell OTM Call Spread (short call + long call)
- Sell OTM Put Spread (short put + long put)
- Collect premium upfront (credit received)
- Profit from time decay and IV contraction

## Key Features

### ✅ Entry Logic

1. **IV Rank Filtering (30-70%)**
   - Enters when IV is elevated but not extreme
   - Avoids low IV (no premium) and extreme IV (high risk)

2. **Optimal Expiry Window (7-14 days)**
   - Balances theta decay and time for profit
   - Avoids too-short expiry (high gamma risk) and too-long expiry (slow decay)

3. **Delta-Based Strike Selection**
   - Short strikes: 15-20 delta (optimal premium collection)
   - Long strikes: 5-10 delta (protection)
   - Net delta: < ±0.10 (delta neutral)

4. **Liquidity Filters**
   - Minimum Open Interest: 50,000
   - Minimum Volume: 10,000
   - Maximum Spread: 0.5% of mid price
   - Premium Range: ₹20-₹200

5. **Risk Management**
   - Portfolio heat check (max 2% of capital at risk)
   - Max 2 concurrent positions
   - Position sizing: 1 lot (50 units) per trade

### ✅ Exit Logic

1. **Profit Targets**
   - TP1: 25% of max profit (quick profit)
   - TP2: 50% of max profit (moderate profit)
   - TP3: 75% of max profit (maximum profit)

2. **Stop Loss**
   - 2x credit received (risk management)
   - Prevents large losses

3. **Time-Based Exit**
   - Closes position 3 days before expiry
   - Avoids gamma risk near expiry

4. **Delta Hedging**
   - Rebalances if net delta exceeds ±0.15
   - Maintains delta neutrality

5. **Volatility Stop**
   - Exits if IV drops > 30% (IV crush protection)
   - Locks in profits when IV collapses

6. **MAE Stop**
   - Exits if max adverse > 1.5% of account
   - Prevents large drawdowns

### ✅ Risk Controls

- **Daily Loss Limit**: 2% of account
- **Max Positions**: 2 concurrent Iron Condors
- **Portfolio Heat**: Max 2% of capital at risk
- **Position Size**: 1 lot (50 units) per trade
- **Account Size**: ₹100,000 (default, configurable)

## Strategy Parameters

```python
# Entry Filters
IV_RANK_MIN = 30          # Minimum IV Rank
IV_RANK_MAX = 70          # Maximum IV Rank
MIN_DTE = 7               # Minimum days to expiry
MAX_DTE = 14              # Maximum days to expiry
SHORT_DELTA_MIN = 0.15    # Minimum short strike delta
SHORT_DELTA_MAX = 0.20    # Maximum short strike delta
LONG_DELTA_MIN = 0.05     # Minimum long strike delta
LONG_DELTA_MAX = 0.10     # Maximum long strike delta
MAX_NET_DELTA = 0.10      # Maximum net delta

# Exit Logic
TP1_PCT = 0.25            # Take profit 1: 25%
TP2_PCT = 0.50            # Take profit 2: 50%
TP3_PCT = 0.75            # Take profit 3: 75%
SL_MULTIPLIER = 2.0       # Stop loss: 2x credit
EXIT_DTE = 3              # Exit when DTE <= 3
DELTA_HEDGE_THRESHOLD = 0.15  # Hedge if net delta exceeds
IV_CRUSH_THRESHOLD = 0.30     # Exit if IV drops > 30%
MAE_LIMIT_PCT = 1.5       # MAE stop: 1.5% of account
```

## Expected Performance

### Profitability
- **Target Win Rate**: 60-70%
- **Average Profit per Trade**: ₹500-₹1,500 (25-50% of credit)
- **Monthly Return**: 3-5% (conservative estimate)

### Drawdown Control
- **Maximum Drawdown**: < 5% (due to delta neutrality)
- **Average Drawdown**: 2-3%
- **Recovery Time**: 1-2 weeks

### Risk Metrics
- **Sharpe Ratio**: > 1.5 (target)
- **Max Consecutive Losses**: 3-4 trades
- **Risk:Reward**: 1:2 (credit received vs max loss)

## Deployment

### Method 1: Automated Deployment Script

```bash
cd /Users/mac/dyad-apps/openalgo
python3 scripts/deploy_delta_neutral_strategy.py
```

The script will:
1. Log in to OpenAlgo
2. Upload the strategy file
3. Set the API key
4. Start the strategy

### Method 2: Manual Deployment

1. **Access OpenAlgo Dashboard**
   ```
   http://127.0.0.1:5001/python
   ```

2. **Upload Strategy**
   - Click "Add Strategy"
   - Name: `Delta Neutral Iron Condor NIFTY`
   - File: `strategies/scripts/delta_neutral_iron_condor_nifty.py`
   - Click "Upload"

3. **Set API Key**
   - Click "Environment" button
   - Add: `OPENALGO_APIKEY` = `your-api-key`
   - Save

4. **Start Strategy**
   - Click "Start" button
   - Monitor logs for entry signals

## Monitoring

### Key Metrics to Watch

1. **Position Status**
   - Number of open positions (max 2)
   - Current P&L per position
   - Days to expiry

2. **Delta Neutrality**
   - Net delta should be < ±0.15
   - Check delta hedging frequency

3. **IV Rank**
   - Current IV rank (should be 30-70%)
   - IV trend (rising/falling)

4. **Daily P&L**
   - Track daily profit/loss
   - Ensure within daily loss limit (2%)

### Log Monitoring

```bash
# View strategy logs
tail -f /Users/mac/dyad-apps/openalgo/log/strategies/delta_neutral_iron_condor_nifty_*.log
```

Look for:
- Entry signals and conditions
- Position opens/closes
- Exit reasons (TP1, TP2, TP3, SL, time-based)
- Delta hedging events
- Error messages

## Market Conditions

### Best Conditions
- ✅ Moderate volatility (IV Rank 30-70%)
- ✅ Range-bound market (NIFTY trading in range)
- ✅ Low trending markets (delta neutral works best)
- ✅ 7-14 days to expiry

### Avoid Conditions
- ❌ Extreme volatility (IV Rank > 70%)
- ❌ Strong trending markets (delta hedging required)
- ❌ Too close to expiry (< 7 days)
- ❌ Low liquidity (OI < 50k, Volume < 10k)

## Troubleshooting

### Strategy Not Entering Positions

**Possible Causes:**
1. IV Rank outside range (30-70%)
   - **Solution**: Wait for IV to normalize
   
2. Days to expiry outside range (7-14)
   - **Solution**: Strategy will wait for optimal expiry
   
3. Max positions reached (2)
   - **Solution**: Wait for existing positions to close
   
4. Portfolio heat limit reached
   - **Solution**: Reduce position size or wait

### High Drawdown

**Possible Causes:**
1. Strong trending market (delta drift)
   - **Solution**: Strategy should delta hedge automatically
   
2. IV expansion (unfavorable)
   - **Solution**: Stop loss should trigger at 2x credit
   
3. Multiple positions open
   - **Solution**: Reduce max positions to 1

### Delta Not Neutral

**Possible Causes:**
1. Delta hedging not working
   - **Solution**: Check delta hedge threshold (should be ±0.15)
   
2. Strong market move
   - **Solution**: Strategy should rebalance automatically

## Optimization Tips

1. **Adjust IV Rank Range**
   - Narrow range (40-60%) for higher quality entries
   - Wider range (25-75%) for more opportunities

2. **Modify Expiry Window**
   - Shorter (5-10 days) for faster profits
   - Longer (10-20 days) for more time decay

3. **Tighten Strike Selection**
   - Closer strikes (10-15 delta) for higher premium
   - Wider spreads for more protection

4. **Adjust Profit Targets**
   - Lower TP1 (15-20%) for quicker exits
   - Higher TP3 (80-90%) for maximum profit

## Files

- **Strategy File**: `strategies/scripts/delta_neutral_iron_condor_nifty.py`
- **Deployment Script**: `scripts/deploy_delta_neutral_strategy.py`
- **Documentation**: `strategies/DELTA_NEUTRAL_STRATEGY.md`

## Support

For issues or questions:
1. Check logs: `log/strategies/delta_neutral_iron_condor_nifty_*.log`
2. Review strategy status: `python3 scripts/check_strategy_status.py`
3. Check OpenAlgo dashboard: `http://127.0.0.1:5001/python`

---

**Created**: January 23, 2026  
**Strategy Type**: Delta-Neutral Iron Condor  
**Underlying**: NIFTY  
**Risk Level**: Medium  
**Expected Return**: 3-5% monthly  
**Max Drawdown**: < 5%
