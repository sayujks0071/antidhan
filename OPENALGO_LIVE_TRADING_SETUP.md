# 🚀 OpenAlgo Live Trading Setup - Complete Checklist

**Date:** January 26, 2026  
**Location:** `/Users/mac/dyad-apps/probable-fiesta/openalgo`  
**Port:** 5001  
**Broker:** Zerodha (Kite Connect)

---

## ✅ STEP 1: VERIFY CONFIGURATION FILES (Already Done)

All configuration files have been copied from your working setup:

- [x] **`.env` file** - ✅ EXISTS
  - Location: `/Users/mac/dyad-apps/probable-fiesta/openalgo/.env`
  - Contains: Kite API credentials, redirect URL, security keys
  - Status: ✅ Configured with `BROKER_API_KEY` and `REDIRECT_URL`

- [x] **Database** - ✅ EXISTS  
  - Location: `/Users/mac/dyad-apps/probable-fiesta/openalgo/db/openalgo.db`
  - Size: 116MB (contains previous trading data)
  - Status: ✅ Copied from working setup

- [x] **Strategy API Keys** - ✅ EXISTS
  - Location: `/Users/mac/dyad-apps/probable-fiesta/openalgo/strategies/strategy_env.json`
  - Status: ✅ Copied from working setup

---

## 💾 BACKUP & RESTORE SETTINGS

**IMPORTANT:** Save your current settings before making changes or at the end of each trading day.

### Quick Backup
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
./QUICK_BACKUP.sh
```

### Full Backup (with .env)
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
python3 scripts/save_settings.py --include-env
```

### List Backups
```bash
python3 scripts/list_backups.py
```

### Restore Settings
```bash
# Interactive restore (select from list)
python3 scripts/restore_settings.py

# Restore latest backup
python3 scripts/restore_settings.py --backup latest

# Restore specific backup
python3 scripts/restore_settings.py --backup 2026-01-27_115500
```

**What Gets Backed Up:**
- Strategy configurations (`strategy_configs.json`)
- Strategy environment variables (`strategy_env.json`)
- Server configuration (`.env` - optional, contains sensitive data)

**Backup Location:** `openalgo/backups/YYYY-MM-DD_HHMMSS/`

---

## ⚠️ STEP 2: START THE SERVER (Required Before Trading)

### Option 1: Using Quick Start Script (Recommended)

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
./QUICK_START.sh
```

### Option 2: Manual Start

```bash
# Navigate to OpenAlgo directory
cd /Users/mac/dyad-apps/probable-fiesta/openalgo

# Activate virtual environment (from working setup)
source /Users/mac/dyad-apps/openalgo/venv/bin/activate

# Start the server
bash start.sh
```

### Option 3: Direct Python Start (If start.sh has issues)

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
source /Users/mac/dyad-apps/openalgo/venv/bin/activate
python3 app.py
```

### Expected Output:
- Server starts on: `http://127.0.0.1:5001`
- WebSocket proxy on: `ws://127.0.0.1:8765`
- You should see: `[OpenAlgo] Starting application on port 5001` or similar

### Verify Server is Running:
```bash
curl http://127.0.0.1:5001/api/v1/ping
# Should return: {"status": "ok"} or similar
```

---

## ⚠️ STEP 3: VERIFY BROKER AUTHENTICATION (Critical)

### Check Authentication Status:

1. **Open Browser:**
   ```
   http://127.0.0.1:5001/auth/login
   ```

2. **Login to OpenAlgo** (create account if first time)

3. **Check Broker Connection:**
   ```
   http://127.0.0.1:5001/auth/broker
   ```

4. **If Token Expired:**
   - Click "Connect Broker"
   - Select "Zerodha"
   - Complete Zerodha login
   - Authorize the app
   - You'll be redirected back

### Or Use Health Check Script:
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
source /Users/mac/dyad-apps/openalgo/venv/bin/activate
python3 scripts/authentication_health_check.py
```

**Expected Result:**
- ✅ KITE CONNECT: Server Running
- ✅ Auth Token: Valid
- ✅ API Test: Connected

---

## ⚠️ STEP 4: VERIFY STRATEGIES CONFIGURATION

### Check Strategy Setup:

1. **Open Strategy Manager:**
   ```
   http://127.0.0.1:5001/python
   ```

2. **Verify Each Strategy:**
   - [ ] Strategies are uploaded
   - [ ] API keys configured (from `strategy_env.json`)
   - [ ] Schedules set: 09:30-15:15 IST
   - [ ] Mode: **PAPER** (for testing) or **LIVE** (real trading)
   - [ ] Symbols configured (NIFTY, BANKNIFTY, etc.)

### Available Strategies:
- `ai_hybrid_reversion_breakout.py`
- `advanced_ml_momentum_strategy.py`
- `supertrend_vwap_strategy.py`
- `orb_strategy.py`
- `trend_pullback_strategy.py`
- (and 5 more)

---

## ⚠️ STEP 5: PRE-TRADING SAFETY CHECKS

### Before Enabling LIVE Mode:

- [ ] **Position Sizes:** Start with 10-25% of target size
- [ ] **Loss Limits Set:**
  - Daily loss limit: ₹5,000 or 5% of account
  - Per-trade loss: ₹1,000
- [ ] **Stop-Loss:** Configured in strategies
- [ ] **Take-Profit:** Levels set
- [ ] **Trading Hours:** 09:30-15:15 IST
- [ ] **Product Type:** MIS (or as configured)

### Recommended First Steps:
1. **Test in PAPER mode** for 1-2 days
2. **Monitor actively** during first few trades
3. **Start small** - one symbol, small position size
4. **Gradually increase** if profitable

---

## 📋 STEP 6: MONITORING SETUP

### Dashboard Access:
- **Main Dashboard:** http://127.0.0.1:5001/dashboard
- **Positions:** http://127.0.0.1:5001/positions
- **Orderbook:** http://127.0.0.1:5001/orderbook
- **Strategy Logs:** http://127.0.0.1:5001/python
- **Tradebook:** http://127.0.0.1:5001/tradebook

### What to Monitor:
- Real-time P&L
- Open positions
- Order status
- Strategy signals
- Entry/exit reasons

---

## 🆘 STEP 7: EMERGENCY PROCEDURES

### If Something Goes Wrong:

1. **Stop All Strategies:**
   - Go to: http://127.0.0.1:5001/python
   - Toggle OFF all strategies

2. **Close Positions:**
   - Go to: http://127.0.0.1:5001/positions
   - Manually close all open positions

3. **Stop Server:**
   ```bash
   # Find process
   lsof -i :5001
   # Kill process
   kill <PID>
   ```

4. **Review Logs:**
   ```bash
   tail -f /Users/mac/dyad-apps/probable-fiesta/openalgo/log/strategies/*.log
   ```

---

## ⏰ TRADING SCHEDULE

- **Market Hours:** 09:15 AM - 03:30 PM IST
- **Trading Window:** 09:30 AM - 03:15 PM IST
- **Session Expiry:** 03:00 AM IST (daily - tokens auto-refresh)

---

## 🔄 DAILY ROUTINE (Before Market Opens)

### Morning Checklist (Before 09:15 AM):

1. **Start Server:**
   ```bash
   cd /Users/mac/dyad-apps/probable-fiesta/openalgo
   ./QUICK_START.sh
   ```
   
   Or manually:
   ```bash
   cd /Users/mac/dyad-apps/probable-fiesta/openalgo
   source /Users/mac/dyad-apps/openalgo/venv/bin/activate
   bash start.sh
   ```

2. **Verify Authentication:**
   ```bash
   python3 scripts/authentication_health_check.py
   ```
   - Should show: ✅ Auth Token: Valid

3. **Check Strategies:**
   - Open: http://127.0.0.1:5001/python
   - Verify all strategies are enabled
   - Check schedules are correct

4. **Monitor Dashboard:**
   - Open: http://127.0.0.1:5001/dashboard
   - Watch for first signals

---

## 📊 QUICK STATUS CHECK

### Quick Status Script:
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
./CHECK_STATUS.sh
```

### Manual Check:
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo

echo "=== OPENALGO STATUS ==="
echo ""
echo "Configuration:"
echo "  .env file: $(test -f .env && echo '✅ EXISTS' || echo '❌ MISSING')"
echo "  Database: $(test -f db/openalgo.db && echo '✅ EXISTS' || echo '❌ MISSING')"
echo "  Strategy env: $(test -f strategies/strategy_env.json && echo '✅ EXISTS' || echo '❌ MISSING')"
echo ""
echo "Server:"
echo "  Port 5001: $(lsof -i :5001 >/dev/null 2>&1 && echo '✅ RUNNING' || echo '❌ NOT RUNNING')"
echo ""
echo "To start server:"
echo "  ./QUICK_START.sh"
```

---

## ✅ FINAL CHECKLIST BEFORE LIVE TRADING

- [ ] Server is running on port 5001
- [ ] Broker authentication is valid (not expired)
- [ ] All strategies configured with API keys
- [ ] Strategies set to correct mode (PAPER/LIVE)
- [ ] Position sizes are conservative
- [ ] Loss limits are set
- [ ] Dashboard is accessible
- [ ] Monitoring tools are ready
- [ ] Emergency stop procedure understood

---

## 📞 QUICK REFERENCE

**Server URL:** http://127.0.0.1:5001  
**Dashboard:** http://127.0.0.1:5001/dashboard  
**Strategies:** http://127.0.0.1:5001/python  
**Broker Auth:** http://127.0.0.1:5001/auth/broker  
**Health Check:** `python3 scripts/authentication_health_check.py`

---

**⚠️ IMPORTANT:** Do not enable LIVE mode until you've tested in PAPER mode and verified everything works correctly!

**Last Updated:** January 26, 2026
