# Fix 403 Errors - Manual Steps Required
**Date:** January 28, 2026, 14:00 IST  
**Status:** ⚠️ Manual intervention required

---

## 🔴 Current Situation

**Problem:** All strategies on port 5001 are getting 403 FORBIDDEN errors (582K+ errors today)

**Root Cause:** API keys are configured in `strategy_env.json` but not properly set in OpenAlgo web UI environment variables for running strategies.

**Automated Fix Status:** ❌ Failed (login/session issues with scripts)

---

## ✅ Solution: Manual Fix via Web UI

### Step 1: Access Strategy Management

1. Open browser: **http://127.0.0.1:5001/python**
2. Login if required:
   - Username: `sayujks0071`
   - Password: `Apollo@20417`

### Step 2: Fix Each Running Strategy

For each strategy showing 403 errors, follow these steps:

#### Affected Strategies (from logs):
- `orb_strategy` (RELIANCE)
- `trend_pullback_strategy` (TCS)
- `sector_momentum_strategy_20260127080141`
- `supertrend_vwap_strategy_20260120112816`
- `mcx_advanced_momentum_strategy`
- `mcx_ai_enhanced_strategy`
- `ai_hybrid_reversion_breakout_20260120112302`
- `crude_oil_enhanced_strategy`
- `mcx_elite_strategy_20260127140511`
- `mcx_neural_strategy_20260127145926`
- `multi_timeframe_momentum_strategy`

#### For Each Strategy:

1. **Find the strategy** in the list at http://127.0.0.1:5001/python

2. **Click "Environment Variables"** (or "Env" button)

3. **Add/Update API Key:**
   - Variable Name: `OPENALGO_APIKEY`
   - Variable Value: `630db05e091812b4c23298ca2d018b62376ddd168860d21fcb4bd2dfc265e49f`
   - Click "Save"

4. **Restart Strategy:**
   - Click "Stop" (if running)
   - Wait 2 seconds
   - Click "Start"
   - Verify status shows "Running"

5. **Verify Fix:**
   - Click "Logs" button
   - Check for successful API calls (200 OK)
   - No more 403 errors

---

## 🔑 API Keys Available

**Primary API Key** (for most strategies):
```
630db05e091812b4c23298ca2d018b62376ddd168860d21fcb4bd2dfc265e49f
```

**Alternative API Key** (for some newer strategies):
```
5258b9b7d21a17843c83da367919c659579ae050889bd3aa3f1f386a90c19163
```

---

## 📋 Quick Checklist

For each strategy:
- [ ] Stop strategy
- [ ] Set `OPENALGO_APIKEY` environment variable
- [ ] Start strategy
- [ ] Verify no 403 errors in logs
- [ ] Check for successful API calls

---

## 🔍 Verification

After fixing, verify:

1. **Check Logs:**
   ```bash
   tail -f /Users/mac/dyad-apps/probable-fiesta/openalgo/log/strategies/<strategy_name>*.log | grep -E "403|200"
   ```

2. **Look for:**
   - ✅ `HTTP/1.1 200 OK` (success)
   - ❌ NO `HTTP/1.1 403 FORBIDDEN` (failure)

3. **Check Strategy Status:**
   - Go to: http://127.0.0.1:5001/python
   - Status should show "Running" with PID
   - No error indicators

---

## ⚡ Quick Fix Script (Alternative)

If you prefer command-line, you can try:

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo

# Get API key from strategy_env.json
API_KEY=$(python3 -c "import json; f=open('strategies/strategy_env.json'); d=json.load(f); print(d['orb_strategy']['OPENALGO_APIKEY'])")

# Export for current session
export OPENALGO_APIKEY="$API_KEY"

# Restart strategies manually via web UI
# Or use curl if you have session cookies
```

---

## 🚨 Important Notes

1. **Rate Limiting:** After fixing 403 errors, you may still see 429 (rate limit) errors. This is normal - strategies will retry automatically.

2. **Session Expiry:** If automated scripts fail due to session expiry, use the web UI method above.

3. **Multiple Strategies:** Fix all strategies systematically - don't skip any.

4. **Verification:** Always verify fixes by checking logs for successful API calls.

---

## 📞 Next Steps After Fix

1. ✅ Monitor logs for 5-10 minutes
2. ✅ Verify strategies are generating signals
3. ✅ Check for entry/exit signals in logs
4. ✅ Monitor API success rate (should be >95%)

---

**Estimated Time:** 10-15 minutes for all strategies  
**Difficulty:** Easy (web UI)  
**Priority:** CRITICAL - Trading is completely halted
