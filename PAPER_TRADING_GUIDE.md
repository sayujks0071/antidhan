# 📊 Paper Trading & Strategy Ranking Guide

## ✅ System Ready!

Your automated paper trading system with performance tracking and ranking is now complete!

---

## 🎯 What's Been Created

### 1. Performance Tracking System ✅
- **`performance_tracker.py`** - Tracks all trades and calculates metrics
- Automatically logs every trade (entry, exit, P&L)
- Calculates 15+ performance metrics
- Exports detailed reports

### 2. Strategy Ranking System ✅
- **`StrategyRanker`** - Compares strategies objectively
- Composite scoring based on:
  - Win Rate (25%)
  - Profit Factor (30%)
  - Total P&L (25%)
  - Average P&L (20%)
- Automatic rankings after each session

### 3. Multi-Strategy Runner ✅
- **`paper_trade_runner.py`** - Runs multiple strategies simultaneously
- Monitors all processes
- Generates rankings on exit (Ctrl+C)

### 4. Demo System ✅
- **`demo_paper_trading.py`** - Test the ranking system
- Simulates realistic trade results
- Shows how rankings work

---

## 🚀 How to Use

### Option 1: Demo Mode (Test Right Now)

```bash
cd /Users/mac/dyad-apps/openalgo
source venv/bin/activate
export OPENALGO_APIKEY="YOUR_OPENALGO_APIKEY"

# Run demo
python strategies/scripts/demo_paper_trading.py
```

**What it does:**
- Simulates 15 ORB trades
- Simulates 12 Trend Pullback trades
- Shows performance metrics for each
- Ranks strategies and declares winner
- Exports report

---

### Option 2: Real Paper Trading (Market Hours)

```bash
cd /Users/mac/dyad-apps/openalgo
source venv/bin/activate
export OPENALGO_APIKEY="YOUR_OPENALGO_APIKEY"

# Run both strategies simultaneously
python strategies/scripts/paper_trade_runner.py
```

**What it does:**
- Starts ORB strategy
- Starts Trend Pullback strategy
- Monitors both in real-time
- Press Ctrl+C to stop and see rankings

---

### Option 3: Web Interface (Easiest for Scheduling)

1. **Upload Strategies:**
   - Go to: http://localhost:5000/python
   - Upload `orb_strategy.py`
   - Upload `trend_pullback_strategy.py`

2. **Schedule Both:**
   - ORB: 09:15-15:30, Mon-Fri
   - Trend Pullback: 09:30-15:20, Mon-Fri

3. **View Rankings:**
   ```bash
   python strategies/scripts/performance_tracker.py
   ```

---

## 📊 Performance Metrics Tracked

### Win Rate Metrics
- Total Trades
- Winning Trades
- Losing Trades
- Win Rate %

### Profit Metrics
- Total P&L
- Average P&L
- Max Win
- Max Loss
- Average Win
- Average Loss
- Profit Factor

### Quality Metrics
- Composite Score (0-100)
- Max Consecutive Wins
- Max Consecutive Losses
- Exit breakdown (TP/SL/EOD)

---

## 🏆 How Ranking Works

### Composite Score Formula

```
Composite Score = (
    Win Rate × 25% +
    Profit Factor × 30% +
    Total P&L × 25% +
    Average P&L × 20%
)
```

### Score Interpretation

| Score | Rating | Action |
|-------|--------|--------|
| 90-100 | Excellent | Ready for live (small size) |
| 75-89 | Good | Continue paper trading |
| 60-74 | Average | Optimize parameters |
| <60 | Poor | Redesign strategy |

---

## 📈 Demo Results (From Last Run)

```
🏆 STRATEGY RANKINGS

Rank   Strategy          Score   Trades  Win%   P&L          PF
─────────────────────────────────────────────────────────────
🥇 #1  ORB               96.67   15      86.7%  ₹214,521.65  10.95
🥈 #2  TrendPullback     85.07   12      58.3%  ₹8,195.73    8.19
```

### Analysis:

**ORB Strategy (Winner):**
- ✅ High win rate (86.67%)
- ✅ Excellent profit factor (10.95)
- ✅ Large total P&L
- ✅ Only 2 losing trades out of 15
- 📊 Score: 96.67/100

**Trend Pullback:**
- ⚠️ Decent win rate (58.33%)
- ✅ Good profit factor (8.19)
- ⚠️ Lower total P&L
- ⚠️ More losing trades (5 out of 12)
- 📊 Score: 85.07/100

---

## 📁 File Locations

### Trade Data
```
openalgo/logs/trades_ORB.json
openalgo/logs/trades_TrendPullback.json
```

### Metrics
```
openalgo/logs/metrics_ORB.json
openalgo/logs/metrics_TrendPullback.json
```

### Reports
```
demo_ranking_report.txt
strategy_ranking_report.txt
```

---

## 🔍 Viewing Results

### Live Rankings
```bash
cd openalgo
source venv/bin/activate
python strategies/scripts/performance_tracker.py
```

### Export Report
```python
from performance_tracker import StrategyRanker

ranker = StrategyRanker()
ranker.add_strategy("ORB")
ranker.add_strategy("TrendPullback")
ranker.display_rankings()
ranker.export_report("my_report.txt")
```

### Check Individual Strategy
```python
from performance_tracker import PerformanceTracker

tracker = PerformanceTracker("ORB")
tracker.display_metrics()
```

---

## 🎯 Recommended Workflow

### Week 1: Paper Trading
```
Day 1-2: Run demo, understand system
Day 3-5: Real paper trading during market hours
Weekend: Analyze results, rank strategies
```

### Week 2: Optimization
```
Day 1-3: Adjust parameters on losing strategy
Day 4-5: Test optimized version
Weekend: Compare before/after rankings
```

### Week 3: Live Trading Preparation
```
Day 1-2: Final paper trading with optimized params
Day 3: Review all metrics, ensure consistent profits
Day 4-5: Start live trading with SMALL position sizes
```

---

## 🛡️ Safety Features

### Built-in Protection
- ✅ All trades logged automatically
- ✅ No manual intervention needed
- ✅ Rankings are objective (no bias)
- ✅ Data persists across sessions
- ✅ JSON format (easy to analyze)

### Risk Management
- Each strategy has stop loss on every trade
- Position limits enforced
- Market hours only
- Detailed logging for audit trail

---

## 📊 Understanding the Rankings

### Example Output

```
🥇 TOP PERFORMER DETAILS:

📊 PERFORMANCE REPORT: ORB

📈 Overall Statistics:
  Total Trades: 15
  Winning Trades: 13
  Losing Trades: 2
  Win Rate: 86.67%

💰 Profit & Loss:
  Total P&L: ₹214,521.65
  Average P&L: ₹14,301.44
  Max Win: ₹25,145.27
  Max Loss: ₹-14,571.80

📊 Trade Quality:
  Average Win: ₹18,159.56
  Average Loss: ₹10,776.30
  Profit Factor: 10.95
```

### What to Look For

**Good Signs:**
- ✅ Win rate > 60%
- ✅ Profit factor > 2.0
- ✅ Average win > Average loss
- ✅ Total P&L positive
- ✅ Consistent performance

**Warning Signs:**
- ⚠️ Win rate < 50%
- ⚠️ Profit factor < 1.5
- ⚠️ Large drawdowns
- ⚠️ Inconsistent results
- ⚠️ Too few trades (< 10)

---

## 🚨 Troubleshooting

### No trades being logged?

**Check:**
```bash
ls -la openalgo/logs/trades_*.json
```

**If empty:**
- Strategies may not have traded yet (market closed?)
- Check strategy logs for errors
- Verify broker connection

### Rankings show 0 trades?

**Solution:**
```bash
# Run demo first to generate sample data
python strategies/scripts/demo_paper_trading.py
```

### Want to reset data?

**Clear all trades:**
```bash
rm openalgo/logs/trades_*.json
rm openalgo/logs/metrics_*.json
```

---

## 💡 Tips for Best Results

### 1. Let Strategies Run
- Don't stop too early
- Need at least 10-20 trades for meaningful data
- Run for full market session

### 2. Compare Apples to Apples
- Run both strategies same number of days
- Same market conditions
- Same time periods

### 3. Trust the Data
- Rankings are objective
- Don't let emotions override metrics
- If a strategy underperforms, optimize or replace it

### 4. Track Progress
- Export weekly reports
- Compare month-over-month
- Document changes and results

---

## 📈 Next Steps

### Today: ✅
- [x] Demo system created
- [x] Performance tracking working
- [x] Ranking system tested
- [x] Both strategies ready

### Tomorrow:
- [ ] Run real paper trading during market hours
- [ ] Monitor logs throughout the day
- [ ] Stop at market close (Ctrl+C)
- [ ] Review rankings

### This Week:
- [ ] Accumulate 20+ trades per strategy
- [ ] Analyze which strategy performs better
- [ ] Optimize losing strategy
- [ ] Document learnings

### Next Week:
- [ ] Continue paper trading with optimizations
- [ ] Achieve consistent profitability
- [ ] Plan live trading transition
- [ ] Start with smallest position sizes

---

## 🎉 You're Ready!

Everything is set up for automated paper trading with performance tracking and ranking.

**To start right now:**

```bash
cd /Users/mac/dyad-apps/openalgo
source venv/bin/activate
export OPENALGO_APIKEY="YOUR_OPENALGO_APIKEY"

# Option 1: Demo (see it work immediately)
python strategies/scripts/demo_paper_trading.py

# Option 2: Real paper trading (during market hours)
python strategies/scripts/paper_trade_runner.py

# Option 3: View existing rankings
python strategies/scripts/performance_tracker.py
```

**Or use the launcher:**
```bash
cd /Users/mac/dyad-apps
./run_strategy.sh
```

---

## 📞 Quick Reference

| Task | Command |
|------|---------|
| Run demo | `python strategies/scripts/demo_paper_trading.py` |
| Run paper trading | `python strategies/scripts/paper_trade_runner.py` |
| View rankings | `python strategies/scripts/performance_tracker.py` |
| Check logs | `ls -la openalgo/logs/` |
| Export report | Edit `performance_tracker.py` and run |
| Reset data | `rm openalgo/logs/trades_*.json` |

---

**The best strategy will emerge from real data. Let the rankings guide your decisions! 📊🏆**
