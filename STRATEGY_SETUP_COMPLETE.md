# ✅ AITRAPP Strategies - Setup Complete!

Your automated trading strategies are ready to use! 🚀

## 🎯 What's Ready

### ✅ API Key Configured
```
46047f09b0d5a7a954d4...f8b12b4a00
```

### ✅ Strategies Created

1. **ORB Strategy** (`orb_strategy.py`)
   - Opening Range Breakout
   - NIFTY, BANKNIFTY, FINNIFTY
   - Ready to run! ✓

2. **Trend Pullback Strategy** (`trend_pullback_strategy.py`)
   - EMA + ATR trend following
   - Top F&O stocks
   - Ready to run! ✓

3. **Options Ranker Strategy** (`options_ranker_strategy.py`)
   - Options spreads template
   - Requires customization

### ✅ OpenAlgo Running
- Status: Active ✓
- URL: http://localhost:5000
- Strategy Manager: http://localhost:5000/python

---

## 🚀 Quick Start (Choose One Method)

### Method 1: Easy Launcher Script (Recommended)

```bash
cd /Users/mac/dyad-apps
./run_strategy.sh
```

Then select:
- `1` for ORB Strategy
- `2` for Trend Pullback
- `4` to test connection
- `5` to open web interface

### Method 2: Direct Command Line

```bash
cd /Users/mac/dyad-apps/openalgo
source venv/bin/activate
export OPENALGO_APIKEY="YOUR_OPENALGO_APIKEY"

# Run ORB strategy
python strategies/scripts/orb_strategy.py

# Or Trend Pullback
python strategies/scripts/trend_pullback_strategy.py
```

### Method 3: Web Interface (Best for Scheduling)

1. Open: http://localhost:5000/python
2. Click "Add Strategy"
3. Upload `orb_strategy.py`
4. Set schedule:
   - Start: 09:15
   - Stop: 15:30
   - Days: Mon-Fri
5. Done! It runs automatically

---

## 📊 Strategy Comparison

| Strategy | Symbols | Timeframe | Difficulty | Status |
|----------|---------|-----------|------------|--------|
| **ORB** | NIFTY, BANKNIFTY, FINNIFTY | 9:15-15:30 | Easy ⭐⭐ | Ready ✅ |
| **Trend Pullback** | Top 10 F&O stocks | 9:30-15:20 | Medium ⭐⭐⭐ | Ready ✅ |
| **Options Ranker** | NIFTY, BANKNIFTY, FINNIFTY | Custom | Advanced ⭐⭐⭐⭐⭐ | Template ⚠️ |

---

## 🛡️ Safety Features (All Included)

- ✅ Automatic stop loss on every trade
- ✅ Position size limits (2-3 max)
- ✅ Market hours only (9:15-15:30)
- ✅ Risk:reward filters (min 1.8-2.5)
- ✅ Volume/liquidity checks
- ✅ Error handling & recovery
- ✅ Detailed logging

---

## 📖 Documentation

All guides are in `openalgo/strategies/`:

1. **QUICKSTART.md** - 5-minute setup guide
2. **AITRAPP_STRATEGIES_GUIDE.md** - Full documentation
3. **README.md** - OpenAlgo strategy system info

---

## 🎯 Recommended First Steps

### For Today:

1. **Test Connection** ✓ (Already done!)
   ```bash
   ./run_strategy.sh
   # Select option 4
   ```

2. **Review Strategy Code**
   ```bash
   cd openalgo/strategies/scripts
   # Read through orb_strategy.py
   # Understand the logic
   ```

3. **Read Documentation**
   ```bash
   cat openalgo/strategies/QUICKSTART.md
   ```

### For Tomorrow (Market Day):

**Option A: Paper Trade First (Recommended)**
- Test with small quantities
- Monitor logs closely
- Verify all features work

**Option B: Schedule Strategy**
1. Go to http://localhost:5000/python
2. Upload ORB strategy
3. Schedule for 09:15-15:30, Mon-Fri
4. Let it run automatically!

---

## 🔍 Monitoring Your Strategies

### Real-time Logs
```bash
# View live logs
tail -f openalgo/logs/strategies/*.log

# Or from launcher
./run_strategy.sh
# Select option to run strategy
```

### Web Dashboard
- Go to: http://localhost:5000/python
- Click "Logs" on any running strategy
- See real-time activity

### Check Positions
- OpenAlgo Dashboard: http://localhost:5000
- View open positions, P&L, order history

---

## ⚙️ Configuration Examples

### Conservative ORB (Safer)
Edit `orb_strategy.py`:
```python
WINDOW_MIN = 20              # Wider range
BREAKOUT_THRESHOLD_PCT = 0.7  # Higher threshold
MAX_POSITIONS = 1            # Single position
RR_MIN = 2.0                 # Better R:R
```

### Aggressive Trend Pullback (More trades)
Edit `trend_pullback_strategy.py`:
```python
EMA_FAST = 21               # Faster signals
MIN_ADX = 20                # Lower trend requirement
MAX_POSITIONS = 3           # More positions
```

---

## 🚨 Troubleshooting

### Strategy won't start?
```bash
# Check API key
echo $OPENALGO_APIKEY

# Test connection
cd /Users/mac/dyad-apps
./run_strategy.sh
# Select option 4
```

### No trades happening?
- Is market open? (9:15-15:30 IST)
- Check logs for filter rejections
- Verify broker is connected in OpenAlgo
- Ensure sufficient margin

### Want to stop strategy?
```bash
# Press Ctrl+C in terminal
# Or from web interface, click "Stop"
```

---

## 📈 What to Expect

### First Run:
- Strategy initializes (~30 seconds)
- Fetches historical data
- Calculates indicators
- Starts monitoring for signals

### During Trading:
- Logs every cycle (30-60 seconds)
- Shows when signals detected
- Displays entry/exit levels
- Tracks positions in real-time

### When Trade Happens:
```
============================================================
[10:45:23] LONG Breakout on NIFTY!
Entry: 21450.50
Stop Loss: 21380.25
TP1: 21520.75
TP2: 21600.50
R:R Ratio: 2.14
Order Response: {'status': 'success', 'orderid': '123456'}
============================================================
```

---

## ✅ Success Checklist

Before going live with real money:

- [ ] Connection test passed ✓
- [ ] Read QUICKSTART.md
- [ ] Understand strategy logic
- [ ] Tested in paper trading mode
- [ ] Monitored logs for 1-2 days
- [ ] Verified stop losses work
- [ ] Checked position sizing
- [ ] Have emergency stop plan
- [ ] Started with small size

---

## 🎓 Learning Resources

### Day 1 (Today): Setup & Testing
- ✅ Setup complete!
- Read QUICKSTART.md
- Test connection
- Review strategy code

### Day 2-3: Paper Trading
- Run ORB strategy during market hours
- Monitor all log messages
- Understand entry/exit logic
- Note any issues

### Week 1: Monitor & Optimize
- Track all trades
- Calculate win rate
- Adjust parameters if needed
- Add second strategy if first works well

---

## 🔒 Security Notes

- ✅ API key is for OpenAlgo only (not stored in cloud)
- ✅ Strategies run locally on your machine
- ✅ All broker communication through OpenAlgo
- ✅ Stop losses protect against large losses

---

## 🎯 Quick Commands Reference

```bash
# Launch menu
./run_strategy.sh

# Direct run ORB
cd openalgo && source venv/bin/activate && \
export OPENALGO_APIKEY="YOUR_OPENALGO_APIKEY" && \
python strategies/scripts/orb_strategy.py

# Direct run Trend Pullback
cd openalgo && source venv/bin/activate && \
export OPENALGO_APIKEY="YOUR_OPENALGO_APIKEY" && \
python strategies/scripts/trend_pullback_strategy.py

# View logs
tail -f openalgo/logs/strategies/*.log

# Open web interface
open http://localhost:5000/python
```

---

## 📞 Next Steps

**Right Now:**
```bash
./run_strategy.sh
```

**Tomorrow (Market Day):**
- Schedule ORB strategy via web interface
- Monitor during market hours
- Review performance

**This Week:**
- Paper trade for 3-5 days
- Track all metrics
- Optimize parameters
- Scale up if profitable

---

## 🎉 You're All Set!

Everything is configured and tested. The strategies are ready to automate your trading!

**Three ways to get started:**

1. **Quick Test**: `./run_strategy.sh` (select option 1)
2. **Web Interface**: http://localhost:5000/python
3. **Read More**: `cat openalgo/strategies/QUICKSTART.md`

Happy Automated Trading! 🚀📈

---

**File Locations:**
- Strategies: `/Users/mac/dyad-apps/openalgo/strategies/scripts/`
- Documentation: `/Users/mac/dyad-apps/openalgo/strategies/`
- Launcher: `/Users/mac/dyad-apps/run_strategy.sh`
- Logs: `/Users/mac/dyad-apps/openalgo/logs/strategies/`
