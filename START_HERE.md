# 🚀 OpenAlgo Live Trading - Start Here

**Everything is organized and ready. Follow these steps in order.**

---

## 📋 CURRENT STATUS

✅ **Configuration Complete:**
- `.env` file with Kite credentials
- Database with previous trading data
- Strategy API keys configured

⚠️ **Action Required:**
- Start the server (see Step 1 below)

---

## 🎯 STEP 1: START THE SERVER

**Before trading each day, run:**

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
./QUICK_START.sh
```

**Or manually:**
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
source /Users/mac/dyad-apps/openalgo/venv/bin/activate
bash start.sh
```

Server will start on: **http://127.0.0.1:5001**

---

## 🔍 STEP 2: CHECK STATUS

**Quick status check:**
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
./CHECK_STATUS.sh
```

**Detailed health check:**
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
source /Users/mac/dyad-apps/openalgo/venv/bin/activate
python3 scripts/authentication_health_check.py
```

---

## ✅ STEP 3: VERIFY BEFORE TRADING

1. **Check Broker Authentication:**
   - Open: http://127.0.0.1:5001/auth/broker
   - If token expired, reconnect Zerodha

2. **Check Strategies:**
   - Open: http://127.0.0.1:5001/python
   - Verify all strategies are enabled
   - Check schedules: 09:30-15:15 IST

3. **Monitor Dashboard:**
   - Open: http://127.0.0.1:5001/dashboard

---

## 📚 COMPLETE DOCUMENTATION

**Full setup guide:** `OPENALGO_LIVE_TRADING_SETUP.md`

**Quick reference:**
- Dashboard: http://127.0.0.1:5001/dashboard
- Strategies: http://127.0.0.1:5001/python
- Broker Auth: http://127.0.0.1:5001/auth/broker
- Positions: http://127.0.0.1:5001/positions

---

## 💾 BACKUP SETTINGS

**Save your settings at the end of each trading day:**

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
./QUICK_BACKUP.sh
```

**Restore settings:**
```bash
python3 scripts/restore_settings.py
```

**List available backups:**
```bash
python3 scripts/list_backups.py
```

---

## ⚠️ IMPORTANT REMINDERS

- **Market Hours:** 09:15 AM - 03:30 PM IST
- **Trading Window:** 09:30 AM - 03:15 PM IST
- **Token Expiry:** 03:00 AM IST (daily)
- **Test in PAPER mode first** before going LIVE
- **Backup settings daily** before closing trading session

---

## 🆘 EMERGENCY STOP

If something goes wrong:
1. Go to: http://127.0.0.1:5001/python → Toggle OFF all strategies
2. Go to: http://127.0.0.1:5001/positions → Close all positions
3. Stop server: `lsof -i :5001` then `kill <PID>`

---

**Last Updated:** January 26, 2026
