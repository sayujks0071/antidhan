# Dhan OpenAlgo Startup Issue
**Date**: January 28, 2026

---

## 🔴 Problem

OpenAlgo is not starting on port 5002. Getting "ERR_CONNECTION_REFUSED" when accessing http://127.0.0.1:5002

---

## 🔍 Root Cause

1. **WebSocket Port Conflict**: Port 8765 is already in use by port 5001 instance
2. **Environment Variables**: FLASK_PORT may not be properly loaded
3. **Process Management**: Multiple attempts to start may have left processes in inconsistent state

---

## ✅ Solution

### Option 1: Start Manually with Explicit Port

```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo

# Load environment
export $(cat .env.dhan | grep -v '^#' | sed "s/'//g" | xargs)

# Explicitly set port
export FLASK_PORT=5002
export APP_MODE=standalone

# Start
python3 app.py
```

### Option 2: Use Port 5001 Instance for Dhan

Since port 5001 is already running, you can:
1. Login to Dhan via http://127.0.0.1:5001
2. Use the same instance for both Kite and Dhan
3. Start option strategies pointing to port 5001

### Option 3: Stop Port 5001 and Use Port 5002

```bash
# Stop port 5001
lsof -ti:5001 | xargs kill -9
lsof -ti:8765 | xargs kill -9

# Start port 5002
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
export $(cat .env.dhan | grep -v '^#' | sed "s/'//g" | xargs)
export FLASK_PORT=5002
python3 app.py
```

---

## 📋 Quick Fix

**Simplest solution**: Use the existing port 5001 instance for Dhan login and option strategies.

1. **Access**: http://127.0.0.1:5001
2. **Login Dhan**: Broker Login → Dhan
3. **Update Option Strategy**: Point to `http://127.0.0.1:5001` instead of `5002`

---

**Status**: ⚠️ Port 5002 startup has issues, recommend using port 5001
