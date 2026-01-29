# AITRAPP Strategies for OpenAlgo

This guide explains how to use the AITRAPP-based trading strategies with OpenAlgo.

## Overview

Three automated trading strategies have been ported from AITRAPP to work with OpenAlgo:

1. **ORB Strategy** - Opening Range Breakout
2. **Trend Pullback Strategy** - EMA + ATR based trend trading
3. **Options Ranker Strategy** - Options spreads (template)

## Quick Start

### Prerequisites

1. OpenAlgo is installed and running
2. Zerodha broker connection is configured
3. API key is generated in OpenAlgo
4. Python dependencies are installed

### Installation Steps

1. **Set Environment Variable**
   ```bash
   export OPENALGO_APIKEY="your-api-key-here"
   ```

2. **Access OpenAlgo Strategy Manager**
   - Open browser and go to: `http://localhost:5000/python`
   - You should see the Strategy Management interface

3. **Upload a Strategy**
   - Click "Add Strategy" button
   - Provide a strategy name (e.g., "ORB NIFTY")
   - Select the strategy file from `strategies/scripts/`
   - Add any custom parameters if needed
   - Click "Upload Strategy"

## Strategy Details

### 1. ORB Strategy (`orb_strategy.py`)

**Description**: Trades breakouts from the first 15 minutes of market open.

**Configuration**:
- **Symbols**: NIFTY, BANKNIFTY, FINNIFTY
- **Opening Range Window**: 15 minutes
- **Breakout Threshold**: 0.5% above/below range
- **Stop Loss**: 50% of opening range
- **Risk:Reward Minimum**: 1.8:1
- **Max Positions**: 2

**How It Works**:
1. Calculates opening range (high/low) from first 15 minutes
2. Waits for price to break above/below range with volume confirmation
3. Enters position with automatic stop loss and take profit levels
4. Manages positions until stop loss or take profit is hit

**Schedule Recommendation**:
- Start Time: 09:15 (market open)
- Stop Time: 15:30 (market close)
- Days: Monday-Friday

**Parameters You Can Customize**:
```python
# Add these as environment parameters in OpenAlgo
SYMBOL=NIFTY             # Change to BANKNIFTY or FINNIFTY
WINDOW_MIN=15            # Opening range window
BREAKOUT_THRESHOLD=0.5   # Breakout threshold %
MAX_POSITIONS=2          # Maximum concurrent positions
```

### 2. Trend Pullback Strategy (`trend_pullback_strategy.py`)

**Description**: Enters on pullbacks in established trends using EMAs and ATR.

**Configuration**:
- **Symbols**: Top 10 liquid F&O stocks
- **EMA Fast/Slow**: 34/89 periods
- **ATR Period**: 14
- **Minimum ADX**: 25 (trend strength)
- **Risk:Reward Minimum**: 2.0:1
- **Max Positions**: 2

**How It Works**:
1. Identifies trend direction using EMA crossover
2. Waits for price to pull back to support/resistance
3. Confirms trend strength with ADX indicator
4. Enters position when pullback completes
5. Uses ATR-based stop loss and profit targets

**Schedule Recommendation**:
- Start Time: 09:30 (avoid opening volatility)
- Stop Time: 15:20
- Days: Monday-Friday

**Monitored Stocks**:
- RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK
- SBIN, BHARTIARTL, ITC, HINDUNILVR, KOTAKBANK

**Parameters You Can Customize**:
```python
EMA_FAST=34              # Fast EMA period
EMA_SLOW=89              # Slow EMA period
ATR_PERIOD=14            # ATR calculation period
MIN_ADX=25               # Minimum ADX for entry
MAX_POSITIONS=2          # Maximum positions
```

### 3. Options Ranker Strategy (`options_ranker_strategy.py`)

**Description**: Template for options spread trading based on IV rank and Greeks.

⚠️ **IMPORTANT**: This is a template strategy that requires:
- Access to live options chain data from your broker
- Proper options pricing and Greeks calculation
- Options-specific order placement logic
- Thorough testing before live deployment

**Configuration**:
- **Symbols**: NIFTY, BANKNIFTY, FINNIFTY
- **Strategy Type**: Debit spreads / Credit spreads
- **IV Rank Range**: 30-70
- **DTE Range**: 3-10 days
- **Delta Range**: 0.30-0.50
- **Max Positions**: 3

**Status**: Template only - requires customization for your broker's options API.

## Using OpenAlgo Strategy Manager

### Starting a Strategy

1. Navigate to `http://localhost:5000/python`
2. Find your uploaded strategy
3. Click "Start" button
4. Monitor logs in real-time

### Scheduling a Strategy

1. Click "Schedule" button on the strategy
2. Set start time (e.g., 09:15)
3. Set stop time (e.g., 15:30)
4. Select days (Mon-Fri for market days)
5. Click "Schedule"

The strategy will now automatically start/stop at specified times!

### Viewing Logs

1. Click "Logs" button to view strategy output
2. Logs show:
   - Entry/exit signals
   - Current positions
   - Order responses
   - Errors and debugging info

### Stopping a Strategy

1. Click "Stop" button to immediately terminate
2. Strategy will attempt graceful shutdown
3. Check logs to confirm all positions closed

## Safety Features

### Risk Management

Each strategy includes:
- **Position Limits**: Maximum concurrent positions
- **Stop Loss**: Automatic stop loss on every trade
- **Take Profit**: Multiple profit target levels
- **Risk:Reward Filter**: Only takes trades with favorable R:R

### Market Hours Protection

- Strategies only trade during market hours (9:15 AM - 3:30 PM IST)
- Automatically skip after-hours
- Reset state at market close

### Error Handling

- Graceful error recovery
- Continues running even if one symbol fails
- Detailed error logging
- Automatic retry logic

## Monitoring Your Strategies

### Key Metrics to Watch

1. **Active Positions**: Number of open trades
2. **Win Rate**: % of profitable trades
3. **Average R:R**: Actual risk:reward achieved
4. **Max Drawdown**: Largest loss from peak
5. **Daily P&L**: Total profit/loss for the day

### Log Messages

- `✅ Buy/Sell Signal`: Entry taken
- `❌ Stop Loss hit`: Position closed at loss
- `💰 Take Profit hit`: Position closed at profit
- `⚠️ Risk filter blocked`: Trade rejected due to risk

## Customization Guide

### Modifying Strategy Parameters

**Option 1: Environment Variables**
```bash
# Set before starting strategy
export SYMBOL=BANKNIFTY
export MAX_POSITIONS=3
export WINDOW_MIN=20
```

**Option 2: Edit Strategy File**
```python
# Edit the strategy file directly
WINDOW_MIN = 20  # Change from 15 to 20
MAX_POSITIONS = 3  # Change from 2 to 3
```

### Adding New Symbols

Edit the `symbols` list in the strategy file:
```python
# ORB Strategy
symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY']

# Trend Pullback Strategy
symbols = ['RELIANCE', 'TCS', 'INFY', 'YOUR_STOCK']
```

### Adjusting Risk Parameters

```python
# Increase/decrease stop loss
STOP_LOSS_PCT = 60  # Was 50

# Adjust minimum R:R
RR_MIN = 2.5  # Was 1.8

# Change position sizing
quantity = calculate_position_size(capital, risk_per_trade)
```

## Troubleshooting

### Strategy Won't Start

**Check**:
- Is `OPENALGO_APIKEY` environment variable set?
- Is OpenAlgo running on localhost:5000?
- Are there any Python syntax errors in logs?

**Solution**:
```bash
# Verify API key
echo $OPENALGO_APIKEY

# Check OpenAlgo is running
curl http://localhost:5000/health

# View detailed logs
tail -f logs/strategies/[strategy_name]_*.log
```

### No Trades Being Placed

**Check**:
- Is it market hours (9:15 AM - 3:30 PM)?
- Are risk filters too strict?
- Is historical data available?
- Are positions already at maximum?

**Solution**:
- Review logs for filter rejections
- Temporarily reduce filter thresholds for testing
- Verify data connection to broker

### Orders Failing

**Check**:
- Is broker account active and logged in?
- Sufficient margin available?
- Are symbols correct for your broker?

**Solution**:
- Check OpenAlgo dashboard for order status
- Verify broker connection in OpenAlgo settings
- Review order rejection messages in logs

### High Memory Usage

**Solution**:
- Reduce lookback period for historical data
- Increase sleep time between cycles
- Monitor fewer symbols simultaneously

## Best Practices

### Before Going Live

1. **Paper Trade First**: Test strategies with paper trading
2. **Review Logs**: Check all log messages make sense
3. **Verify Orders**: Ensure orders placed correctly
4. **Test Stop Loss**: Confirm stop losses trigger properly
5. **Check Margin**: Ensure sufficient margin for max positions

### Daily Operations

1. **Pre-Market**:
   - Verify OpenAlgo is running
   - Check broker connection
   - Review previous day's P&L

2. **During Market**:
   - Monitor active positions
   - Check logs periodically
   - Verify orders executing correctly

3. **Post-Market**:
   - Review all trades
   - Calculate daily P&L
   - Analyze what worked/didn't work
   - Archive logs for record-keeping

### Risk Management Rules

1. **Never risk more than 1-2% per trade**
2. **Set maximum daily loss limit**
3. **Don't override stop losses**
4. **Keep position sizes small initially**
5. **Gradually scale up after consistent profits**

## Performance Tracking

### Metrics to Track

Create a trading journal with:
- Date and time of trades
- Entry/exit prices
- Profit/loss per trade
- Reason for entry (which signal)
- Lessons learned

### Analysis

Weekly review:
- Which strategy performed best?
- Which symbols are most profitable?
- What time of day has best results?
- Are filters working as intended?

## Support & Updates

### Getting Help

1. Check OpenAlgo documentation
2. Review strategy logs for errors
3. Test with minimal configuration first
4. Verify broker API connectivity

### Upgrading Strategies

When new versions are released:
1. Backup current strategy files
2. Test new version in paper trading
3. Compare performance with old version
4. Gradually migrate if improved

## Disclaimer

**IMPORTANT**: These strategies are for educational purposes.

- Always test thoroughly in paper trading first
- Past performance does not guarantee future results
- Trading involves substantial risk of loss
- Never trade with money you cannot afford to lose
- Consult a financial advisor before live trading

## Summary

You now have three powerful automated trading strategies integrated with OpenAlgo:

1. **ORB Strategy**: Fast-moving breakout trades
2. **Trend Pullback**: Trend-following with pullback entries
3. **Options Ranker**: Options spread template (requires customization)

Start with paper trading, monitor carefully, and scale up gradually once comfortable with the system.

**Happy Trading! 📈**
