# Troubleshooting Connection Refused Error

## Server Status: ✅ Running

The OpenAlgo server is running on port 5001 (PID: 44269).

## Possible Causes

### 1. Browser Cache
- **Clear browser cache** or use **incognito/private mode**
- Try a different browser

### 2. Wrong URL
Make sure you're using:
- ✅ `http://127.0.0.1:5001` (correct)
- ✅ `http://localhost:5001` (also works)
- ❌ `https://127.0.0.1:5001` (wrong - no HTTPS)
- ❌ `http://127.0.0.1:5002` (wrong port)

### 3. Firewall/Security Software
- Check if macOS Firewall is blocking connections
- System Preferences → Security & Privacy → Firewall
- Temporarily disable to test

### 4. Server Binding Issue
The server should be binding to `127.0.0.1` or `0.0.0.0`. Let's verify.

## Quick Fixes

### Option 1: Restart Server
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
pkill -f "python.*app.py"
sleep 2
./scripts/start_port5001_kite.sh
```

### Option 2: Test Connection
```bash
# Test if server responds
curl http://127.0.0.1:5001/

# Test API endpoint
curl http://127.0.0.1:5001/api/v1/ping
```

### Option 3: Check Server Logs
```bash
tail -f /tmp/openalgo_5001_restart.log
```

## Verification Steps

1. **Check server is running**:
   ```bash
   lsof -i :5001
   ```

2. **Test connection**:
   ```bash
   curl http://127.0.0.1:5001/
   ```

3. **Try in browser**:
   - Use incognito/private window
   - Navigate to: `http://127.0.0.1:5001`
   - Or: `http://localhost:5001`

## If Still Not Working

1. **Kill all Python processes** and restart:
   ```bash
   pkill -9 -f "python.*app.py"
   sleep 3
   cd /Users/mac/dyad-apps/probable-fiesta/openalgo
   ./scripts/start_port5001_kite.sh
   ```

2. **Check for port conflicts**:
   ```bash
   lsof -i :5001
   ```

3. **Try a different port** (if needed):
   ```bash
   FLASK_PORT=5003 python3 app.py
   ```

---

**Current Status**: Server is running on port 5001. Try the fixes above.
