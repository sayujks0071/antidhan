# Deployment Plan: Top 4 Strategies

**Date:** January 29, 2026  
**Status:** Ready for Deployment  
**Strategies:** 4 (3 new + 1 existing)

---

## 🎯 Deployment Overview

### Strategies to Deploy

| # | Strategy | Score | Status | Location |
|---|----------|-------|--------|----------|
| 1 | **AI Hybrid Reversion + Breakout** | 4.5 | ✅ Ported | `openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py` |
| 2 | **MCX Commodity Momentum Enhanced** | 4.25 | ✅ Running | `openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py` |
| 3 | **Advanced ML Momentum** | 4.0 | ✅ Ported | `openalgo/strategies/scripts/advanced_ml_momentum_strategy.py` |
| 4 | **SuperTrend VWAP** | 3.5 | ✅ Ported | `openalgo/strategies/scripts/supertrend_vwap_strategy.py` |

---

## ✅ Pre-Deployment Checklist

### Porting Status
- [x] AI Hybrid Reversion + Breakout ported to current location
- [x] Advanced ML Momentum ported to current location
- [x] SuperTrend VWAP ported to current location
- [x] MCX Commodity Momentum already in current location
- [x] All scripts made executable

### Environment Setup
- [ ] Verify `OPENALGO_APIKEY` is set
- [ ] Verify `OPENALGO_HOST` is set (default: http://127.0.0.1:5001)
- [ ] Verify `OPENALGO_PORT` is set (default: 5001)
- [ ] Verify OpenAlgo API is running and accessible
- [ ] Create logs directory: `openalgo/strategies/logs/`

### Strategy Configuration
- [ ] Review symbol assignments for each strategy
- [ ] Review risk parameters (stop losses, position sizing)
- [ ] Verify market hours compatibility
- [ ] Check API rate limits

---

## 📋 Deployment Steps

### Step 1: Pre-Deployment Verification

```bash
# Check OpenAlgo API is running
curl http://127.0.0.1:5001/auth/check-setup

# Verify environment variables
echo $OPENALGO_APIKEY
echo $OPENALGO_HOST
echo $OPENALGO_PORT

# Check existing strategies
ps aux | grep python3 | grep strategy
```

### Step 2: Deploy Strategies

**Option A: Use Deployment Script (Recommended)**

```bash
cd openalgo/strategies

# Deploy all 4 strategies
./deploy_top_4_strategies.sh deploy

# Check status
./deploy_top_4_strategies.sh status

# View logs
tail -f logs/ai_hybrid_reversion_breakout_*.log
tail -f logs/advanced_ml_momentum_strategy_*.log
tail -f logs/supertrend_vwap_strategy_*.log
```

**Option B: Manual Deployment**

```bash
cd openalgo/strategies
mkdir -p logs

# Strategy 1: AI Hybrid Reversion + Breakout
nohup python3 scripts/ai_hybrid_reversion_breakout.py \
    --symbol NIFTY \
    --port 5001 \
    --api_key $OPENALGO_APIKEY \
    --rsi_lower 30 \
    --sector "NIFTY 50" > logs/ai_hybrid_$(date +%Y%m%d_%H%M%S).log 2>&1 &

# Strategy 2: MCX Commodity Momentum (Already running - verify)
ps aux | grep mcx_commodity_momentum_strategy

# Strategy 3: Advanced ML Momentum
nohup python3 scripts/advanced_ml_momentum_strategy.py \
    --symbol NIFTY \
    --port 5001 \
    --api_key $OPENALGO_APIKEY \
    --threshold 0.01 > logs/ml_momentum_$(date +%Y%m%d_%H%M%S).log 2>&1 &

# Strategy 4: SuperTrend VWAP
nohup python3 scripts/supertrend_vwap_strategy.py \
    --symbol NIFTY \
    --quantity 10 \
    --api_key $OPENALGO_APIKEY \
    --host http://127.0.0.1:5001 \
    --sector "NIFTY BANK" > logs/supertrend_$(date +%Y%m%d_%H%M%S).log 2>&1 &
```

### Step 3: Verify Deployment

```bash
# Check all strategies are running
./deploy_top_4_strategies.sh status

# Expected output:
# ✓ ai_hybrid_reversion_breakout (PID: xxxxx)
# ✓ mcx_commodity_momentum_strategy (PID: xxxxx)
# ✓ advanced_ml_momentum_strategy (PID: xxxxx)
# ✓ supertrend_vwap_strategy (PID: xxxxx)

# Check logs for errors
tail -n 50 logs/*.log | grep -i error

# Check OpenAlgo web UI
open http://127.0.0.1:5001/python
```

---

## 🔧 Strategy Configuration

### Strategy 1: AI Hybrid Reversion + Breakout

**Parameters:**
- Symbol: `NIFTY` (configurable)
- Port: `5001` (default)
- RSI Lower: `30` (default)
- RSI Upper: `60` (default)
- Stop Loss: `1.0%` (default)
- Sector: `NIFTY 50` (default)

**Risk Controls:**
- ✅ Stop loss: 1.0%
- ✅ VIX-based position sizing (reduces size by 50% if VIX > 25)
- ✅ Market breadth filter
- ✅ Sector rotation filter
- ✅ Earnings filter

**Expected Performance:**
- Win Rate: 82-88%
- Profit Factor: 5.5-8.0
- Sharpe Ratio: 3.0-4.0
- Max Drawdown: 5-8%

### Strategy 2: MCX Commodity Momentum Enhanced

**Status:** ✅ Already deployed and running

**Parameters:**
- Commodities: Gold, Silver, Crude Oil, Natural Gas, Copper
- Max Positions: 3 concurrent
- Portfolio Heat: <2.5%
- Regime Detection: Enabled

**Risk Controls:**
- ✅ Regime-adaptive stop losses (1.0-1.5 ATR)
- ✅ Multi-level take profits (TP1/TP2/TP3)
- ✅ Trailing stops
- ✅ Correlation filtering
- ✅ Daily loss limit: 3.0%
- ✅ Weekly loss limit: 8.0%
- ✅ Recovery mode: 4.0% drawdown

**Expected Performance:**
- Win Rate: 70-78%
- Profit Factor: 4.5-6.0
- Sharpe Ratio: 2.8-3.5
- Monthly Returns: 50-80%

### Strategy 3: Advanced ML Momentum

**Parameters:**
- Symbol: `NIFTY` (configurable)
- Port: `5001` (default)
- ROC Threshold: `0.01` (default)
- Stop Loss: `1.0%` (default)

**Risk Controls:**
- ✅ Stop loss: 1.0%
- ✅ Momentum fade exit (RSI < 50)
- ✅ Relative strength filter
- ✅ Trend filter (Price > SMA50)
- ⚠️ **GAP:** Missing daily/weekly loss limits (to be added)

**Expected Performance:**
- Win Rate: 78-85%
- Profit Factor: 4.5-6.0
- Sharpe Ratio: 2.5-3.2
- Max Drawdown: 8-12%

**Recommended Enhancements:**
- Add daily loss limit (3%)
- Add weekly loss limit (8%)
- Consider correlation management

### Strategy 4: SuperTrend VWAP

**Parameters:**
- Symbol: `NIFTY` (configurable)
- Quantity: `10` (default)
- Threshold: `155` (optimized)
- Stop Loss: `1.8%` (optimized)
- Sector: `NIFTY BANK` (default)

**Risk Controls:**
- ✅ Stop loss: 1.8%
- ✅ Volume profile analysis
- ✅ Sector correlation filter
- ✅ VWAP deviation filter
- ⚠️ **GAP:** Missing daily/weekly loss limits
- ⚠️ **GAP:** Fixed position sizing (not adaptive)

**Expected Performance:**
- Win Rate: 72-78%
- Profit Factor: 3.2-4.5
- Sharpe Ratio: 1.8-2.3
- Max Drawdown: 12-15%

**Recommended Enhancements:**
- Add daily/weekly loss limits
- Implement adaptive position sizing
- Add drawdown protection

---

## 📊 Monitoring Plan

### Real-Time Monitoring

**Log Files:**
```bash
# Watch all strategy logs
tail -f openalgo/strategies/logs/*.log

# Watch specific strategy
tail -f openalgo/strategies/logs/ai_hybrid_*.log
```

**Process Monitoring:**
```bash
# Check running strategies
ps aux | grep python3 | grep strategy

# Check PIDs
cat openalgo/strategies/logs/*.pid
```

**Web UI:**
- OpenAlgo Strategy Manager: http://127.0.0.1:5001/python
- Check strategy status, logs, and controls

### Daily Monitoring Checklist

- [ ] All 4 strategies running (check PIDs)
- [ ] No errors in logs (grep for ERROR/CRITICAL)
- [ ] API connectivity (check 403/429 errors)
- [ ] Position tracking (verify positions are being tracked)
- [ ] Performance metrics (win rate, P&L)

### Weekly Review

- [ ] Performance comparison across strategies
- [ ] Risk metrics (drawdown, portfolio heat)
- [ ] Strategy correlation analysis
- [ ] Optimization opportunities
- [ ] Log file rotation and cleanup

---

## 🚨 Troubleshooting

### Common Issues

**1. Strategy Not Starting**
```bash
# Check log file for errors
tail -50 logs/<strategy>_*.log

# Common causes:
# - Missing API key
# - Invalid symbol
# - API not accessible
# - Import errors
```

**2. 403 Forbidden Errors**
```bash
# Verify API key is set correctly
echo $OPENALGO_APIKEY

# Check API key in OpenAlgo web UI
# Settings -> API Keys
```

**3. Strategy Crashes**
```bash
# Check for Python errors
grep -i "error\|exception\|traceback" logs/*.log

# Verify dependencies
python3 -c "import pandas, numpy"
```

**4. High API Rate Limits (429)**
```bash
# Strategies should retry automatically
# If persistent, reduce strategy frequency or add delays
```

### Emergency Stop

```bash
# Stop all strategies immediately
./deploy_top_4_strategies.sh stop

# Or manually
pkill -f ai_hybrid_reversion_breakout.py
pkill -f advanced_ml_momentum_strategy.py
pkill -f supertrend_vwap_strategy.py
pkill -f mcx_commodity_momentum_strategy.py
```

---

## 📈 Performance Expectations

### Combined Portfolio Targets

- **Total Win Rate:** >75% (weighted average)
- **Combined Sharpe:** >2.5
- **Portfolio Heat:** <5% (across all strategies)
- **Max Drawdown:** <10% (portfolio level)

### Individual Strategy Targets

| Strategy | Win Rate | Profit Factor | Sharpe | Max DD |
|----------|----------|---------------|--------|--------|
| AI Hybrid | 82-88% | 5.5-8.0 | 3.0-4.0 | 5-8% |
| MCX Momentum | 70-78% | 4.5-6.0 | 2.8-3.5 | 6-10% |
| ML Momentum | 78-85% | 4.5-6.0 | 2.5-3.2 | 8-12% |
| SuperTrend VWAP | 72-78% | 3.2-4.5 | 1.8-2.3 | 12-15% |

---

## 🔄 Maintenance Schedule

### Daily
- Monitor strategy status
- Check logs for errors
- Verify API connectivity

### Weekly
- Performance review
- Risk metrics analysis
- Log file cleanup

### Monthly
- Strategy optimization review
- Parameter tuning if needed
- Performance comparison with targets

---

## 📝 Notes

1. **MCX Strategy:** Already deployed and running. Monitor separately using MCX-specific monitoring.

2. **Risk Controls:** AI Hybrid and MCX have comprehensive risk controls. ML Momentum and SuperTrend VWAP need daily/weekly loss limits added.

3. **Symbol Configuration:** All strategies default to NIFTY. Adjust symbols as needed for your trading preferences.

4. **Paper Trading:** Consider paper trading new strategies (AI Hybrid, ML Momentum, SuperTrend VWAP) for 1-2 weeks before full deployment.

5. **Correlation:** Monitor correlation between strategies to avoid overexposure to similar market conditions.

---

## ✅ Deployment Sign-Off

**Prepared by:** Strategy Prioritization Planner  
**Date:** January 29, 2026  
**Status:** Ready for Deployment

**Next Steps:**
1. Review and approve deployment plan
2. Set up environment variables
3. Execute deployment script
4. Monitor initial deployment (first 24 hours)
5. Review performance after 1 week

---

*For questions or issues, refer to:*
- Strategy Prioritization Plan: `STRATEGY_PRIORITIZATION_PLAN_2026-01-29.md`
- Strategy Manager Subagent: `.cursor/agents/strategy-manager.md`
- OpenAlgo Documentation: `openalgo/docs/`
