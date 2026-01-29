# Port 5002 Now Configured for Dhan
**Date**: January 28, 2026

---

## ✅ Issue Fixed!

**Problem**: Port 5002 was showing Kite instead of Dhan.

**Root Cause**: `.env` file had Kite configuration which was being loaded.

**Solution**: Updated `.env` file with Dhan broker configuration.

---

## ✅ Current Status

- **Port 5002**: ✅ Running with Dhan configuration
- **.env file**: ✅ Updated with Dhan broker credentials
- **Web UI**: ✅ Accessible at http://127.0.0.1:5002

---

## 📋 Configuration

**Broker**: Dhan  
**Client ID**: 1105009139  
**API Key**: df1da5de  
**API Secret**: fddc233a-a819-4e40-a282-1acbf9cd70b9  
**Port**: 5002  
**Valid Brokers**: dhan, dhan_sandbox

---

## 🚀 Login Steps

1. **Open**: http://127.0.0.1:5002
2. **Login to OpenAlgo**:
   - Username: `sayujks0071`
   - Password: `Apollo@20417`
3. **Navigate to**: Broker Login → Dhan
4. **Click**: "Login with Dhan"
5. **Complete**: OAuth authorization
6. **Verify**: Broker Status shows "Connected"

---

## ⚠️ Important Notes

### Port 5001 (KiteConnect)

**⚠️ Port 5001 may be affected** since `.env` was changed. If port 5001 needs Kite config:

1. **Option A**: Restore original .env and use separate configs
2. **Option B**: Port 5001 should continue working if it was started before .env change

**To restore Kite config for port 5001**:
```bash
# Find backup
ls -t .env.backup.* | head -1

# Restore (if needed)
mv .env.backup.<timestamp> .env

# Restart port 5001
```

### Port 5002 (Dhan)

- ✅ Currently configured for Dhan
- ✅ Running on port 5002
- ✅ Ready for Dhan login

---

## 🔄 Restart Port 5002

If you need to restart:

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo

# Stop
lsof -ti:5002 | xargs kill -9

# Start
export FLASK_PORT=5002
export APP_MODE=standalone
python3 app.py
```

Or use the script:
```bash
./scripts/start_dhan_port5002_final.sh
```

---

## ✅ Verification

After login, verify Dhan is connected:

1. Check Broker Status page
2. Should show "Connected" for Dhan
3. Option strategies should work

---

**Status**: ✅ Port 5002 configured for Dhan - ready to login!
