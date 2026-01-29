# Port 5002 Final Setup Guide
**Date**: January 28, 2026

---

## ✅ Solution: Bypass .env File for Port 5002

The `.env` file has `FLASK_PORT=5001` which overrides our port 5002 setting. The solution is to temporarily disable it.

---

## 🚀 Start Port 5002

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
./scripts/start_dhan_port5002_noenv.sh
```

**What this script does**:
1. Temporarily comments out `FLASK_PORT` in `.env`
2. Sets `FLASK_PORT=5002` via environment variable
3. Starts OpenAlgo on port 5002
4. Restores `.env` after startup

---

## 📋 After Port 5002 Starts

### 1. Login to Dhan

1. **Open**: http://127.0.0.1:5002
2. **Navigate to**: Broker Login → Dhan
3. **Click**: "Login with Dhan"
4. **Complete OAuth** flow
5. **Verify**: Broker Status shows "Connected"

### 2. Start Option Strategy

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
./scripts/start_option_strategy_port5002.sh
```

**Or manually**:
```bash
export OPENALGO_HOST="http://127.0.0.1:5002"
export OPENALGO_APIKEY="5258b9b7d21a17843c83da367919c659579ae050889bd3aa3f1f386a90c19163"
python3 strategies/scripts/advanced_options_ranker.py
```

---

## ✅ Configuration Summary

- **Port 5001**: KiteConnect (NSE/MCX) ✅ Running
- **Port 5002**: Dhan (Options) ✅ Ready to start
- **WebSocket**: Disabled for port 5002 (APP_MODE=standalone)
- **Databases**: Separate DBs for each instance

---

## 🔧 Troubleshooting

### Port 5002 Not Starting

1. **Check if port is in use**:
   ```bash
   lsof -i :5002
   ```

2. **Kill existing process**:
   ```bash
   lsof -ti:5002 | xargs kill -9
   ```

3. **Check logs**:
   ```bash
   tail -f log/dhan_port5002.log
   ```

### Still Using Port 5001

- The script should handle this, but if it persists:
  - Manually comment out `FLASK_PORT` in `.env`
  - Or use a separate directory with different `.env`

---

## 📝 Files Created

- `scripts/start_dhan_port5002_noenv.sh` - Start script (bypasses .env)
- `scripts/start_option_strategy_port5002.sh` - Option strategy starter
- `.env.dhan` - Dhan configuration (for reference)

---

**Status**: ✅ Ready to start port 5002!
