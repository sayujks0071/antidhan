# Restart PR #48 Strategies - Manual Guide

## Strategies Updated in PR #48

1. **advanced_ml_momentum_strategy** - Relaxed entry conditions (RSI: 55→50, Volume: 0.8x→0.5x)
2. **mcx_global_arbitrage_strategy** - Added argument parsing for --port and --api_key

---

## Manual Restart Steps

### Step 1: Access Web UI
1. Open browser: **http://127.0.0.1:5001/python**
2. Login if required:
   - Username: `sayujks0071`
   - Password: `Apollo@20417`

### Step 2: Restart `advanced_ml_momentum_strategy`

1. **Find the strategy** in the list:
   - Look for: **"advanced_ml_momentum_strategy"**
   - Current Status: Should show "Running" with PID

2. **Stop the strategy**:
   - Click the **"Stop"** button
   - Wait 2-3 seconds for it to stop
   - Status should change to "Stopped"

3. **Start the strategy**:
   - Click the **"Start"** button
   - Wait 2-3 seconds
   - Status should show "Running" with a new PID

4. **Verify**:
   - Check that status shows "Running"
   - Click **"View Logs"** to verify it started correctly
   - Look for: "Starting Advanced ML Momentum Strategy"

### Step 3: Restart `mcx_global_arbitrage_strategy`

1. **Find the strategy** in the list:
   - Look for: **"mcx_global_arbitrage_strategy"**
   - Current Status: May show "Stopped" (had 403 error)

2. **Verify API Key** (if stopped):
   - Click **"Environment Variables"** button
   - Check that `OPENALGO_APIKEY` is set
   - If not set, add it:
     - Key: `OPENALGO_APIKEY`
     - Value: `5258b9b7d21a17843c83da367919c659579ae050889bd3aa3f1f386a90c19163`
     - Click **"Save"**

3. **Start the strategy**:
   - Click the **"Start"** button
   - Wait 2-3 seconds
   - Status should show "Running" with a PID

4. **Verify**:
   - Check that status shows "Running"
   - Click **"View Logs"** to verify no 403 errors
   - Look for: "Starting MCX Global Arbitrage Strategy"

---

## Verification

### Check Logs

**For advanced_ml_momentum_strategy**:
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
tail -f log/strategies/advanced_ml_momentum_strategy*.log
```

**Look for**:
- ✅ "Starting Advanced ML Momentum Strategy"
- ✅ "Strong Momentum Signal" messages (should see more with relaxed conditions)
- ✅ Order placement messages (if conditions are met)

**For mcx_global_arbitrage_strategy**:
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
tail -f log/strategies/mcx_global_arbitrage_strategy*.log
```

**Look for**:
- ✅ "Starting MCX Global Arbitrage Strategy"
- ✅ No "403 Forbidden" errors
- ✅ API calls succeeding

---

## Expected Results

### After Restart

1. **advanced_ml_momentum_strategy**:
   - ✅ Should generate more signals (relaxed RSI and volume thresholds)
   - ✅ Should place more orders (if market conditions meet new thresholds)
   - ✅ Logs should show "Strong Momentum Signal" more frequently

2. **mcx_global_arbitrage_strategy**:
   - ✅ Should start without 403 errors (with proper API key)
   - ✅ Should accept --port and --api_key arguments
   - ✅ Should run successfully with argument parsing

---

## Troubleshooting

### If strategies don't start:

1. **Check API Key**:
   - Verify `OPENALGO_APIKEY` is set in Environment Variables
   - Test API key: `python3 strategies/scripts/test_api_key.py <api_key>`

2. **Check Server Status**:
   - Verify OpenAlgo server is running: `ps aux | grep "python.*app.py"`
   - Check server logs for errors

3. **Check Rate Limits**:
   - If getting 429 errors, wait 1-2 minutes and try again
   - Clear browser cookies if needed

4. **Check Logs**:
   - Review strategy logs for specific error messages
   - Check for missing dependencies or import errors

---

## Quick Command Reference

```bash
# Check strategy status
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
cat strategies/strategy_configs.json | python3 -c "import sys, json; d=json.load(sys.stdin); [print(f\"{v.get('name')}: Running={v.get('is_running')}, PID={v.get('pid')}\") for k,v in d.items() if 'advanced_ml' in v.get('name','').lower() or 'mcx_global' in v.get('name','').lower()]"

# Monitor logs
tail -f log/strategies/advanced_ml_momentum_strategy*.log
tail -f log/strategies/mcx_global_arbitrage_strategy*.log

# Check if strategies are running
ps aux | grep -E "advanced_ml_momentum|mcx_global_arbitrage" | grep -v grep
```

---

**Created**: January 28, 2026, 11:45 IST  
**Related**: PR #48 Merge Confirmation  
**Status**: Ready for manual restart
