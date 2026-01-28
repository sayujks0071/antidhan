# 🚨 LIVE TRADING PRE-FLIGHT CHECKLIST
**Date:** January 26, 2026  
**Broker:** Zerodha (Kite Connect)  
**Port:** 5001

## ⚠️ CRITICAL ISSUES FOUND

### 1. ❌ MISSING .env FILE
**Status:** NOT CONFIGURED  
**Impact:** System cannot start without this file  
**Action Required:**
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
cp .sample.env .env
# Then edit .env and configure:
# - BROKER_API_KEY (from https://developers.kite.trade/)
# - BROKER_API_SECRET (from https://developers.kite.trade/)
# - REDIRECT_URL = 'http://127.0.0.1:5001/zerodha/callback'
# - APP_KEY (generate: python -c "import secrets; print(secrets.token_hex(32))")
# - API_KEY_PEPPER (generate another one)
```

### 2. ❌ DATABASE NOT INITIALIZED
**Status:** Database file not found  
**Impact:** Cannot store broker authentication tokens  
**Action Required:**
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 scripts/init_db.py
```

### 3. ❌ SERVER NOT RUNNING
**Status:** Port 5001 not in use  
**Impact:** Cannot connect to broker or run strategies  
**Action Required:**
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
# Start server (choose one method):
# Method 1: Using start.sh
bash start.sh

# Method 2: Using gunicorn directly
gunicorn --worker-class eventlet --workers 1 --bind 0.0.0.0:5001 --timeout 120 app:app
```

### 4. ❌ BROKER AUTHENTICATION NOT COMPLETE
**Status:** Cannot verify (server not running)  
**Impact:** Strategies cannot place orders  
**Action Required:**
1. Start server (see #3)
2. Open browser: http://127.0.0.1:5001/auth/login
3. Login to OpenAlgo
4. Go to: http://127.0.0.1:5001/auth/broker
5. Select "Zerodha" and click "Connect Broker"
6. Complete Zerodha login and authorization
7. Verify token is stored in database

### 5. ❌ STRATEGY API KEYS NOT CONFIGURED
**Status:** strategy_env.json not found  
**Impact:** Strategies cannot authenticate with OpenAlgo API  
**Action Required:**
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo/strategies
# Create strategy_env.json with your OpenAlgo API keys
# Format:
{
  "strategy_id_1": {
    "OPENALGO_APIKEY": "your_api_key_here"
  },
  "strategy_id_2": {
    "OPENALGO_APIKEY": "your_api_key_here"
  }
}
```

---

## ✅ VERIFICATION STEPS

### Step 1: Verify .env Configuration
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 -c "from utils.env_check import load_and_check_env_variables; load_and_check_env_variables()"
```
**Expected:** No errors, all variables validated

### Step 2: Verify Server Startup
```bash
# Check if server responds
curl http://127.0.0.1:5001/api/v1/ping
```
**Expected:** `{"status": "ok"}` or similar

### Step 3: Verify Broker Authentication
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 scripts/authentication_health_check.py
```
**Expected:** 
- ✅ KITE CONNECT: Server Running
- ✅ Auth Token: Valid
- ✅ API Test: Connected

### Step 4: Verify Strategy Configuration
1. Open: http://127.0.0.1:5001/python
2. Check that strategies are uploaded
3. Verify each strategy has API key configured
4. Check strategy schedules (should be 09:30-15:15 IST)

### Step 5: Test API Connectivity
```bash
# Replace YOUR_API_KEY with actual API key
curl -X POST http://127.0.0.1:5001/api/v1/funds \
  -H "Content-Type: application/json" \
  -d '{"apikey": "YOUR_API_KEY"}'
```
**Expected:** Account balance/funds information

---

## 📋 PRE-TRADING SAFETY CHECKS

### Risk Management Settings
- [ ] Position sizes configured (start with 10-25% of target)
- [ ] Daily loss limit set (e.g., ₹5,000 or 5% of account)
- [ ] Per-trade loss limit set (e.g., ₹1,000)
- [ ] Stop-loss configured in strategies
- [ ] Take-profit levels configured

### Strategy Configuration
- [ ] All strategies set to **PAPER** mode initially (for testing)
- [ ] Symbol lists verified (NIFTY, BANKNIFTY, etc.)
- [ ] Trading hours: 09:30-15:15 IST
- [ ] Interval: 5m (or as configured)
- [ ] Product type: MIS (or as configured)

### Monitoring Setup
- [ ] Log directory accessible: `openalgo/log/strategies/`
- [ ] Dashboard accessible: http://127.0.0.1:5001/dashboard
- [ ] Positions page accessible: http://127.0.0.1:5001/positions
- [ ] Orderbook accessible: http://127.0.0.1:5001/orderbook
- [ ] Strategy logs accessible: http://127.0.0.1:5001/python

---

## 🔧 QUICK FIX COMMANDS

### Complete Setup (Run in order):
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo

# 1. Create .env from sample
cp .sample.env .env
# EDIT .env with your credentials

# 2. Initialize database
python3 scripts/init_db.py

# 3. Start server
bash start.sh

# 4. In browser: Login and connect broker
# http://127.0.0.1:5001/auth/login
# http://127.0.0.1:5001/auth/broker

# 5. Create strategy_env.json
mkdir -p strategies
cat > strategies/strategy_env.json << 'EOF'
{
  "ai_hybrid": {
    "OPENALGO_APIKEY": "YOUR_API_KEY_HERE"
  },
  "ml_momentum": {
    "OPENALGO_APIKEY": "YOUR_API_KEY_HERE"
  },
  "supertrend_vwap": {
    "OPENALGO_APIKEY": "YOUR_API_KEY_HERE"
  }
}
EOF
# EDIT with actual API keys

# 6. Verify everything
python3 scripts/authentication_health_check.py
```

---

## 🚨 EMERGENCY STOP PROCEDURE

If something goes wrong during live trading:

1. **Immediate Stop:**
   - Go to: http://127.0.0.1:5001/python
   - Toggle OFF all strategies
   - Or kill server: `pkill -f "gunicorn.*5001"`

2. **Close Positions:**
   - Go to: http://127.0.0.1:5001/positions
   - Manually close all open positions

3. **Review Logs:**
   - Check: `openalgo/log/strategies/*.log`
   - Check dashboard logs

---

## 📞 SUPPORT RESOURCES

- **OpenAlgo Dashboard:** http://127.0.0.1:5001/dashboard
- **Strategy Management:** http://127.0.0.1:5001/python
- **Broker Connection:** http://127.0.0.1:5001/auth/broker
- **Documentation:** See README.md and LIVE_TRADING_QUICK_START.txt

---

## ⏰ MARKET TIMINGS

- **Market Hours:** 09:15 AM - 03:30 PM IST
- **Trading Window:** 09:30 AM - 03:15 PM IST
- **Session Expiry:** 03:00 AM IST (daily)

---

**⚠️ DO NOT ENABLE LIVE MODE UNTIL ALL CHECKS ARE COMPLETE!**
