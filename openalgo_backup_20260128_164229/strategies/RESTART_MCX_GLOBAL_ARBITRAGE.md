# Restart MCX Global Arbitrage Strategy - 403 Error Fixed ✅

## Issue Fixed
The strategy was updated to properly read `OPENALGO_APIKEY` from environment variables (as set by OpenAlgo), not just from command-line arguments.

## Changes Made
- ✅ Strategy now reads `OPENALGO_APIKEY` from environment variables
- ✅ Falls back to command-line arguments for manual testing
- ✅ Properly handles both `OPENALGO_HOST` and `OPENALGO_PORT` environment variables

## Restart Instructions

### Step 1: Verify API Key is Set
The API key should already be configured in `strategy_env.json`:
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
cat strategies/strategy_env.json | python3 -c "import sys, json; d=json.load(sys.stdin); print('API Key:', d.get('mcx_global_arbitrage_strategy_20260128110030', {}).get('OPENALGO_APIKEY', 'NOT SET')[:30] + '...')"
```

Expected output: `API Key: 5258b9b7d21a17843c83da367919c6...`

### Step 2: Restart Strategy via Web UI

1. **Open**: http://127.0.0.1:5001/python
2. **Login** if needed (username: `sayujks0071`)
3. **Find**: `mcx_global_arbitrage_strategy` in the list
4. **Click**: **"Start"** button
5. **Wait**: 2-3 seconds
6. **Verify**: Status shows "Running" with a PID

### Step 3: Verify No 403 Errors

**Check Logs**:
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
tail -f log/strategies/mcx_global_arbitrage_strategy*.log
```

**Look for**:
- ✅ "Starting MCX Global Arbitrage Strategy for..."
- ✅ "Fetching data for..."
- ❌ NO "403 Forbidden" errors
- ❌ NO "Invalid API key" errors

## Expected Result

After restart:
- ✅ Strategy starts successfully
- ✅ No 403 errors
- ✅ API key properly read from environment
- ✅ Strategy runs and logs arbitrage signals

## Troubleshooting

### If 403 error persists:

1. **Check API Key in Environment Variables**:
   - Go to: http://127.0.0.1:5001/python
   - Click "Environment Variables" on the strategy
   - Verify `OPENALGO_APIKEY` is set to: `5258b9b7d21a17843c83da367919c659579ae050889bd3aa3f1f386a90c19163`
   - If not set, add it and save, then restart

2. **Test API Key**:
   ```bash
   python3 strategies/scripts/test_api_key.py 5258b9b7d21a17843c83da367919c659579ae050889bd3aa3f1f386a90c19163
   ```

3. **Check Server Logs**:
   ```bash
   tail -f log/*.log | grep -i "403\|forbidden\|api"
   ```

---

**Status**: ✅ Fixed and ready to restart  
**File Updated**: `openalgo/strategies/scripts/mcx_global_arbitrage_strategy.py`  
**Commit**: Pushed to main branch
