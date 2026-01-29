# Port 5002 Setup Success
**Date**: January 28, 2026

---

## ✅ Port 5002 is Working!

**Status**: Port 5002 is accessible and responding!

---

## 🌐 Access Port 5002

**Web UI**: http://127.0.0.1:5002

**API**: http://127.0.0.1:5002/api/v1/

---

## 📋 Next Steps

### 1. Login to Dhan

1. **Open**: http://127.0.0.1:5002
2. **Navigate to**: Broker Login → Dhan
3. **Click**: "Login with Dhan"
4. **Complete OAuth** flow
5. **Verify**: Broker Status shows "Connected"

### 2. Update Option Strategy to Use Port 5002

The option strategy is currently configured for port 5001. Update it:

**Via Environment Variable**:
```bash
export OPENALGO_HOST="http://127.0.0.1:5002"
export OPENALGO_APIKEY="5258b9b7d21a17843c83da367919c659579ae050889bd3aa3f1f386a90c19163"
python3 strategies/scripts/advanced_options_ranker.py
```

**Or update the script default**:
- Change `API_HOST` in `strategies/scripts/advanced_options_ranker.py` to `http://127.0.0.1:5002`

### 3. Start Option Strategy

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
export OPENALGO_HOST="http://127.0.0.1:5002"
export OPENALGO_APIKEY="5258b9b7d21a17843c83da367919c659579ae050889bd3aa3f1f386a90c19163"
python3 strategies/scripts/advanced_options_ranker.py
```

---

## ✅ Configuration Summary

- **Port 5001**: KiteConnect (NSE/MCX strategies) ✅ Running
- **Port 5002**: Dhan (Options strategies) ✅ Running
- **WebSocket**: Disabled for port 5002 (avoiding conflict)
- **Databases**: Separate DBs for each instance

---

## 🎯 Benefits of Separate Ports

1. ✅ **No Broker Conflicts**: Kite and Dhan can both be logged in
2. ✅ **Isolated Sessions**: Each broker has its own session
3. ✅ **Separate Databases**: Clean separation of data
4. ✅ **Independent Management**: Start/stop independently

---

**Status**: ✅ Port 5002 ready for Dhan login!
