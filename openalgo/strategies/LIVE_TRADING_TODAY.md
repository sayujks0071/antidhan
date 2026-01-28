# Live Trading Setup for Today

## ✅ Optimization Status
- **Status**: Running in background
- **Process**: Check with `ps aux | grep optimize_strategies`
- **Log File**: `openalgo/strategies/optimization.log`
- **Monitor**: `tail -f openalgo/strategies/optimization.log`

## 🚀 Quick Start for Live Trading

### Step 1: Verify Server is Running
```bash
# Check if server is running
lsof -i :5001 | grep LISTEN

# If not running, start it:
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 app.py &
```

### Step 2: Check Broker Authentication
1. **Open Browser**: http://127.0.0.1:5001/auth/broker
2. **Login** if required (username: `sayujks0071`)
3. **Verify Broker Connection**:
   - If you see "Connect Broker" → Click and authenticate with Zerodha/Kite
   - If you see "Connected" → ✅ Ready for trading
   - If token expired → Reconnect broker

### Step 3: Access Strategy Manager
1. **Open**: http://127.0.0.1:5001/python
2. **Login** if required
3. You'll see all available strategies

### Step 4: Start Strategies for Live Trading

#### Option A: Using Web UI (Recommended)
1. Go to: http://127.0.0.1:5001/python
2. For each strategy you want to trade:
   - Click **"Start"** button
   - Or click **"Enable"** if it's scheduled
3. Verify status shows "Running"

#### Option B: Using Script
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
export OPENALGO_USERNAME="sayujks0071"
export OPENALGO_PASSWORD="Apollo@20417"
python3 scripts/start_live_trading.py --all
```

### Step 5: Monitor Live Trading
- **Dashboard**: http://127.0.0.1:5001/dashboard
- **Positions**: http://127.0.0.1:5001/positions
- **Strategy Logs**: Click "Logs" button on each strategy
- **Orders**: http://127.0.0.1:5001/orders

## 📋 Pre-Trading Checklist

Before starting live trading:

- [ ] ✅ Server is running on port 5001
- [ ] ✅ Broker (Zerodha/Kite) is authenticated
- [ ] ✅ API key is set: `5258b9b7d21a17843c83da367919c659579ae050889bd3aa3f1f386a90c19163`
- [ ] ✅ Strategies are uploaded to OpenAlgo
- [ ] ✅ Strategies are configured with correct symbols
- [ ] ✅ Trading schedule is set (09:30-15:15 IST)
- [ ] ✅ Risk parameters are configured
- [ ] ⚠️ **Test in PAPER mode first** before going LIVE

## 🎯 Available MCX Strategies

Based on your setup, you have these MCX strategies:

1. **Natural Gas Clawdbot Strategy**
   - File: `natural_gas_clawdbot_strategy.py`
   - Symbol: NATURALGAS24FEB26FUT
   - Exchange: MCX

2. **Crude Oil Enhanced Strategy**
   - File: `crude_oil_enhanced_strategy.py`
   - Symbol: CRUDEOIL19FEB26FUT
   - Exchange: MCX

3. **Other MCX Strategies** (if uploaded)
   - Check at: http://127.0.0.1:5001/python

## ⚠️ Important Notes

### Market Hours (IST)
- **MCX Trading**: 09:00 AM - 11:30 PM (varies by commodity)
- **Natural Gas**: Check MCX schedule
- **Crude Oil**: Check MCX schedule

### Risk Management
- Start with **PAPER mode** to test
- Use small position sizes initially
- Set appropriate stop-loss and take-profit levels
- Monitor positions actively

### Emergency Stop
If something goes wrong:
1. Go to: http://127.0.0.1:5001/python
2. Click **"Stop"** on all running strategies
3. Go to: http://127.0.0.1:5001/positions
4. Close any open positions manually if needed

## 📊 Monitoring Commands

```bash
# Check optimization progress
tail -f openalgo/strategies/optimization.log

# Check server status
curl http://127.0.0.1:5001/api/v1/ping

# Check running strategies
curl -s http://127.0.0.1:5001/api/v1/strategies | python3 -m json.tool

# Monitor positions
curl -s http://127.0.0.1:5001/api/v1/positions | python3 -m json.tool
```

## 🔄 Today's Trading Plan

1. **Morning (Before Market Open)**:
   - ✅ Verify server is running
   - ✅ Check broker authentication
   - ✅ Review strategy configurations
   - ✅ Set trading schedules

2. **Market Hours**:
   - ✅ Monitor strategies via dashboard
   - ✅ Watch for entry/exit signals
   - ✅ Track positions and P&L

3. **End of Day**:
   - ✅ Review trading performance
   - ✅ Check optimization results (if complete)
   - ✅ Backup settings
   - ✅ Close any remaining positions

## 📞 Quick Links

- **Strategy Manager**: http://127.0.0.1:5001/python
- **Dashboard**: http://127.0.0.1:5001/dashboard
- **Broker Auth**: http://127.0.0.1:5001/auth/broker
- **Positions**: http://127.0.0.1:5001/positions
- **Orders**: http://127.0.0.1:5001/orders

---

**Ready to trade?** Start with Step 2 above to verify broker authentication!
