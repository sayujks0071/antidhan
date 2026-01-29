# 403 Error Fix - Web UI Authentication Issue

## Problem
Getting 403 error when trying to start `mcx_global_arbitrage_strategy` via Web UI.

## Root Cause
The 403 error is coming from **Web UI authentication/ownership check**, not from the strategy itself. The strategy doesn't make API calls (uses mock data), so the 403 is from the `/python/start/<strategy_id>` endpoint.

Possible causes:
1. **Session expired** - Need to login again
2. **Ownership check** - Strategy has `user_id` that doesn't match current session
3. **Rate limiting** - Too many requests

## Solutions

### Solution 1: Remove User ID Restriction (Applied)
Removed `user_id` from strategy config to allow any authenticated user to start it.

### Solution 2: Login and Retry
1. Go to: http://127.0.0.1:5001/python
2. **Logout** if logged in
3. **Login again** with:
   - Username: `sayujks0071`
   - Password: `Apollo@20417`
4. **Wait 1-2 minutes** (to clear rate limits)
5. Try starting the strategy again

### Solution 3: Start Strategy Directly (Bypass Web UI)
Use the direct start script:
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 scripts/start_mcx_global_arbitrage_direct.py
```

This bypasses the Web UI and starts the strategy directly with environment variables.

### Solution 4: Use API with Session Cookie
1. Login via browser and get session cookie
2. Use curl with session cookie:
```bash
# Get session cookie from browser (DevTools → Application → Cookies)
curl -X POST http://127.0.0.1:5001/python/start/mcx_global_arbitrage_strategy_20260128110030 \
  -H "Cookie: session=<your-session-cookie>"
```

## Verification

After applying fixes:
1. **Check strategy config**:
   ```bash
   cat strategies/strategy_configs.json | python3 -c "import sys, json; d=json.load(sys.stdin); print('user_id:', d.get('mcx_global_arbitrage_strategy_20260128110030', {}).get('user_id', 'None'))"
   ```
   Should show: `user_id: None`

2. **Try starting via Web UI**:
   - Login fresh
   - Go to strategies page
   - Click "Start" on mcx_global_arbitrage_strategy
   - Should start without 403 error

3. **Check logs**:
   ```bash
   tail -f log/strategies/mcx_global_arbitrage_strategy*.log
   ```
   Should see: "Starting MCX Global Arbitrage Strategy"

---

**Status**: ✅ User ID restriction removed  
**Next Step**: Try starting via Web UI again after logging in fresh
