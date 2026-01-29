# Start Trading Now - Quick Guide

## ✅ Found Strategies Ready to Start

The system found **3 stopped strategies**:
1. `advanced_equity_strategy`
2. `advanced_options_ranker`
3. `mcx_advanced_strategy`

## 🚀 Start Strategies via Web UI (Easiest Method)

### Step 1: Open Strategy Manager
```
http://127.0.0.1:5001/python
```

### Step 2: Login (if required)
- Username: `sayujks0071`
- Password: `Apollo@20417`

### Step 3: Start Each Strategy
For each of the 3 strategies:
1. Find the strategy in the list
2. Click the **"Start"** button
3. Verify status changes to "Running"

## 🔍 Alternative: Check Strategy Details

To see what each strategy does:

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 scripts/start_live_trading.py
# (without --all flag, shows strategy details)
```

## ⚠️ Before Starting

1. **Verify Broker Authentication**:
   - Go to: http://127.0.0.1:5001/auth/broker
   - Ensure broker (Zerodha/Kite) is connected

2. **Check Strategy Configuration**:
   - Symbols are correct
   - Trading schedule is set
   - Risk parameters are appropriate

3. **Start with PAPER Mode** (if available):
   - Test strategies in paper trading first
   - Switch to LIVE only after verification

## 📊 Monitor After Starting

- **Dashboard**: http://127.0.0.1:5001/dashboard
- **Positions**: http://127.0.0.1:5001/positions
- **Strategy Logs**: Click "Logs" button on each strategy

## 🛑 Emergency Stop

If you need to stop all strategies:
1. Go to: http://127.0.0.1:5001/python
2. Click "Stop" on each running strategy
3. Or use: `python3 scripts/stop_all_strategies.py` (if available)

---

**Quick Action**: Open http://127.0.0.1:5001/python in your browser and click "Start" on each strategy!
