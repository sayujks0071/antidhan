# Port 5002 Dhan Configuration Fixed
**Date**: January 28, 2026

---

## ✅ Issue Fixed

**Problem**: Port 5002 was showing Kite instead of Dhan because `.env` file (with Kite config) was overriding Dhan environment variables.

**Solution**: Created a separate `.env` file with Dhan configuration for port 5002.

---

## 🔧 What Was Done

1. **Created separate .env**: Port 5002 now uses its own `.env` file with Dhan config
2. **Preserved original .env**: Port 5001 continues using original `.env` (Kite)
3. **Verified configuration**: Dhan broker credentials are correctly set

---

## 📋 Current Configuration

### Port 5001 (KiteConnect)
- **Broker**: Kite/Zerodha
- **Config**: Original `.env` file
- **Status**: ✅ Running

### Port 5002 (Dhan)
- **Broker**: Dhan
- **Config**: Separate `.env` file (created by script)
- **Status**: ✅ Running with Dhan config

---

## 🚀 Start Port 5002

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
./scripts/start_dhan_port5002_with_dhan_env.sh
```

**What this script does**:
1. Backs up original `.env`
2. Creates new `.env` with Dhan configuration
3. Starts OpenAlgo on port 5002
4. Restores original `.env` (but port 5002 keeps using its config)

---

## 📋 Login Steps

1. **Open**: http://127.0.0.1:5002
2. **Login to OpenAlgo**: sayujks0071 / Apollo@20417
3. **Go to**: Broker Login → Dhan
4. **Click**: "Login with Dhan"
5. **Complete**: OAuth authorization
6. **Verify**: Broker Status shows "Connected"

---

## ✅ Verification

After starting port 5002, verify Dhan config:

```bash
# Check broker API key in process
ps e -p $(lsof -ti:5002) | grep BROKER_API_KEY

# Should show: 1105009139:::df1da5de (Dhan)
```

---

## 🔄 Restart Port 5002

If you need to restart:

```bash
# Stop
lsof -ti:5002 | xargs kill -9

# Start
./scripts/start_dhan_port5002_with_dhan_env.sh
```

---

**Status**: ✅ Port 5002 configured for Dhan!
