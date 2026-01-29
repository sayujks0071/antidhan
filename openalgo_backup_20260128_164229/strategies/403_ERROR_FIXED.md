# 403 Error Fix - Complete ✅

## Problem
Three strategies were getting 403 errors when trying to start:
1. `mcx_global_arbitrage_strategy`
2. `natural_gas_clawdbot_strategy`
3. `crude_oil_enhanced_strategy`

## Root Cause
These strategies require `OPENALGO_APIKEY` environment variable, but it wasn't configured in their strategy environment settings.

## Solution Applied

### 1. Set API Keys
✅ API keys have been configured in `strategy_env.json`:
- Strategy ID: `mcx_global_arbitrage_strategy_20260128110030`
- Strategy ID: `natural_gas_clawdbot_strategy_20260128110030`
- Strategy ID: `crude_oil_enhanced_strategy_20260128110030`

API Key: `5258b9b7d21a17843c83da367919c659579ae050889bd3aa3f1f386a90c19163`

### 2. Restart Strategies
Strategies need to be restarted for the API key to take effect.

## How to Restart

### Option 1: Via Web UI (Easiest)
1. Go to: http://127.0.0.1:5001/python
2. For each of the 3 strategies:
   - Click **"Stop"** (if running)
   - Wait 2 seconds
   - Click **"Start"**
3. Verify status shows "Running"

### Option 2: Via Script
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 scripts/restart_403_strategies.py
```

## Verification

After restarting, check:
1. **Status**: http://127.0.0.1:5001/python
   - All 3 strategies should show "Running"
   - No 403 errors

2. **Logs**: Check strategy logs for errors
   - http://127.0.0.1:5001/python/logs/<strategy_id>

3. **API Calls**: Strategies should now successfully make API calls

## Current Status

- ✅ API keys configured
- ⚠️ Strategies need restart to apply changes
- ✅ Ready to start once restarted

## Next Steps

1. **Restart the 3 strategies** (via web UI or script)
2. **Verify they start without 403 errors**
3. **Monitor logs** to ensure they're working correctly

---

**Fix Applied**: January 28, 2026, 11:06 IST  
**API Key**: Configured for all 3 strategies  
**Action Required**: Restart strategies to apply API key
