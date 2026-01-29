# 403 Error Fix - Manual Steps Required

## Status
✅ **API Key is VALID** and has been set in `strategy_env.json`  
⚠️ **Rate limits (429)** are preventing automated restart  
✅ **Manual restart via Web UI required**

## API Key Verification
- **API Key**: `5258b9b7d21a17843c83da367919c659579ae050889bd3aa3f1f386a90c19163`
- **Status**: ✅ VALID (tested successfully)
- **Location**: Set in `strategies/strategy_env.json` for all 3 strategies

## Affected Strategies
1. `mcx_global_arbitrage_strategy`
2. `natural_gas_clawdbot_strategy`
3. `crude_oil_enhanced_strategy`

## Manual Fix Steps

### Step 1: Wait for Rate Limit to Clear
- Rate limit errors (429) occur when too many requests are made
- **Wait 1-2 minutes** before proceeding

### Step 2: Access Web UI
1. Open: **http://127.0.0.1:5001/python**
2. Login if required:
   - Username: `sayujks0071`
   - Password: `Apollo@20417`

### Step 3: Restart Each Strategy
For each of the 3 strategies:

1. **Find the strategy** in the list
2. **Click "Stop"** (if it shows as running)
   - Wait 2-3 seconds
3. **Click "Start"**
   - Wait 2-3 seconds
4. **Verify Status**:
   - Should show "Running" with a PID
   - No 403 errors in the status

### Step 4: Verify API Key is Loaded
1. Click **"Environment Variables"** button on each strategy
2. Check that `OPENALGO_APIKEY` is set
3. If not set, add it:
   - Key: `OPENALGO_APIKEY`
   - Value: `5258b9b7d21a17843c83da367919c659579ae050889bd3aa3f1f386a90c19163`
   - Click "Save"
   - Then restart the strategy

### Step 5: Check Logs
1. Click **"View Logs"** on each strategy
2. Look for:
   - ✅ No "403 Forbidden" errors
   - ✅ No "Invalid API key" errors
   - ✅ Successful API calls

## Alternative: Wait and Retry Script
If you prefer automated fix, wait 2 minutes then run:
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 scripts/fix_403_proper.py
```

## Expected Result
After restarting:
- All 3 strategies show "Running" status
- No 403 errors
- Total running strategies: **20** (17 current + 3 fixed)

## Troubleshooting

### If 403 error persists:
1. **Verify API key** is correct in Environment Variables
2. **Check strategy logs** for specific error message
3. **Test API key** manually:
   ```bash
   cd /Users/mac/dyad-apps/probable-fiesta/openalgo
   python3 strategies/scripts/test_api_key.py 5258b9b7d21a17843c83da367919c659579ae050889bd3aa3f1f386a90c19163
   ```

### If rate limit (429) persists:
1. **Wait 5 minutes** for rate limit to reset
2. **Clear browser cookies** for `127.0.0.1:5001`
3. **Use incognito/private window**

---

**Last Updated**: January 28, 2026, 11:10 IST  
**API Key**: ✅ Valid and configured  
**Action**: Manual restart required via Web UI
