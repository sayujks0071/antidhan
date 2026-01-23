# Quick Start Guide - AITRAPP Strategies on OpenAlgo

Get your automated trading strategies running in 5 minutes!

## Step 1: Get Your API Key

1. Open OpenAlgo: `http://localhost:5000`
2. Go to Settings → API
3. Click "Generate API Key"
4. Copy the API key

## Step 2: Set Environment Variable

```bash
# For current session
export OPENALGO_APIKEY="your-api-key-here"

# Or add to your shell profile for persistence
echo 'export OPENALGO_APIKEY="your-api-key-here"' >> ~/.zshrc
source ~/.zshrc
```

## Step 3: Access Strategy Manager

1. Open: `http://localhost:5000/python`
2. You'll see the Strategy Management dashboard

## Step 4: Upload Your First Strategy

### ORB Strategy (Recommended for Beginners)

1. Click "Add Strategy"
2. **Name**: `ORB NIFTY`
3. **File**: Select `orb_strategy.py` from `strategies/scripts/`
4. **Parameters** (Optional):
   - `SYMBOL`: NIFTY
   - `WINDOW_MIN`: 15
   - `MAX_POSITIONS`: 2
5. Click "Upload Strategy"

## Step 5: Schedule the Strategy

1. Click "Schedule" button on your strategy
2. **Start Time**: `09:15` (market open)
3. **Stop Time**: `15:30` (market close)
4. **Days**: Select Mon, Tue, Wed, Thu, Fri
5. Click "Schedule"

## Step 6: Start Trading!

### For Immediate Start
- Click the "Start" button

### For Scheduled Start
- Strategy will automatically start at 09:15 tomorrow

### Monitor Your Strategy
- Click "Logs" to view real-time activity
- Watch for entry/exit signals
- Check positions in OpenAlgo dashboard

## Available Strategies

### 1. ORB Strategy (`orb_strategy.py`)
- **Best For**: Volatile opening sessions
- **Symbols**: NIFTY, BANKNIFTY, FINNIFTY
- **Time**: 09:15 - 15:30
- **Difficulty**: ⭐⭐ Easy

### 2. Trend Pullback (`trend_pullback_strategy.py`)
- **Best For**: Trending markets
- **Symbols**: Liquid F&O stocks
- **Time**: 09:30 - 15:20
- **Difficulty**: ⭐⭐⭐ Medium

### 3. Options Ranker (`options_ranker_strategy.py`)
- **Best For**: Options traders
- **Status**: Template - requires customization
- **Difficulty**: ⭐⭐⭐⭐⭐ Advanced

## Quick Configuration Examples

### Conservative ORB
```python
WINDOW_MIN=20           # Wider opening range
BREAKOUT_THRESHOLD=0.7  # Higher breakout confirmation
MAX_POSITIONS=1         # Single position only
RR_MIN=2.0             # Better risk:reward
```

### Aggressive Trend Pullback
```python
EMA_FAST=21            # Faster EMA
EMA_SLOW=55            # Medium-term EMA
MIN_ADX=20             # Lower trend requirement
MAX_POSITIONS=3        # More positions
```

## Testing Checklist

Before going live:

- [ ] API key is set correctly
- [ ] Broker is connected in OpenAlgo
- [ ] Strategy uploaded successfully
- [ ] Schedule configured for market hours
- [ ] Logs are showing activity
- [ ] Paper trading enabled (if available)
- [ ] Stop loss levels verified
- [ ] Position sizing appropriate

## Common Commands

### Check if strategy is running
```bash
# View active processes
ps aux | grep python | grep strategy

# Check logs
tail -f logs/strategies/ORB_*.log
```

### Stop a strategy manually
```bash
# From OpenAlgo UI - click "Stop" button
# OR from command line
pkill -f orb_strategy.py
```

### View today's logs
```bash
cd logs/strategies/
ls -lt | head -10
```

## Safety Limits

Default limits for all strategies:
- **Max Positions**: 2-3 per strategy
- **Stop Loss**: Automatic on every trade
- **Market Hours**: 9:15 AM - 3:30 PM only
- **Risk:Reward**: Minimum 1.8-2.5 depending on strategy

## What to Expect

### First Hour
- Strategy initializes
- Fetches historical data
- Calculates indicators
- Looks for entry signals

### During Trading
- Logs show every cycle
- Positions tracked in real-time
- Orders placed automatically
- Stop losses monitored

### End of Day
- Positions may be held overnight (MIS will auto-square-off)
- Logs archived
- Ready for next day

## Troubleshooting

### "OPENALGO_APIKEY not set"
```bash
export OPENALGO_APIKEY="your-key"
python strategies/scripts/orb_strategy.py
```

### "Cannot connect to OpenAlgo"
```bash
# Check if OpenAlgo is running
curl http://localhost:5000/health

# Restart if needed
cd openalgo
python app.py
```

### "No trades happening"
- Check if market is open
- Review logs for filter rejections
- Verify symbols are correct
- Ensure sufficient margin

## Next Steps

1. **Start with ORB Strategy** - Easiest to understand
2. **Monitor for 1 week** - Paper trade or small size
3. **Review performance** - Analyze wins/losses
4. **Optimize parameters** - Adjust based on results
5. **Scale up gradually** - Increase position size carefully

## Support

For issues:
1. Check `AITRAPP_STRATEGIES_GUIDE.md` for detailed docs
2. Review strategy logs for error messages
3. Verify OpenAlgo broker connection
4. Test with single symbol first

## Success Tips

✅ **DO**:
- Start with paper trading
- Keep position sizes small
- Monitor logs regularly
- Track all trades
- Review daily performance

❌ **DON'T**:
- Trade with money you can't afford to lose
- Override stop losses manually
- Run multiple instances of same strategy
- Ignore error messages
- Scale up too quickly

---

**Ready to automate your trading? Start with ORB strategy and follow the steps above!**

📈 Happy Automated Trading!
