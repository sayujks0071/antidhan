# Fix Start Button Issues

## Common Causes

1. **Master Contracts Not Ready** (Most Common)
   - Blocks ALL strategy starts
   - Solution: Click "Check & Start" button on the Python Strategies page
   - Or visit: http://127.0.0.1:5001/python/ and click the master contract button

2. **CSRF Token Missing**
   - Check browser console (F12) for errors
   - Solution: Refresh the page (Ctrl+R or Cmd+R)

3. **Session Expired**
   - Solution: Re-login to OpenAlgo

4. **File Not Found**
   - Check if strategy file exists
   - Solution: Re-upload the strategy

5. **JavaScript Errors**
   - Check browser console (F12)
   - Solution: Clear cache and reload

## Quick Fixes

### Option 1: Check Master Contracts
1. Go to: http://127.0.0.1:5001/python/
2. Look for "Master Contract" status card
3. Click "Check & Start" button if contracts are not ready
4. Wait for initialization to complete
5. Try starting strategies again

### Option 2: Check Browser Console
1. Press F12 to open developer tools
2. Go to "Console" tab
3. Click a start button
4. Look for any red error messages
5. Share the error message for debugging

### Option 3: Check Server Logs
```bash
cd /Users/mac/dyad-apps/openalgo
tail -f log/*.log | grep -i "start\|error\|master"
```

### Option 4: Manual Start via API
Use the restart script:
```bash
cd /Users/mac/dyad-apps/openalgo
source venv/bin/activate
export OPENALGO_USERNAME="YOUR_OPENALGO_USERNAME"
export OPENALGO_PASSWORD="YOUR_OPENALGO_PASSWORD"
python3 scripts/restart_strategies.py --strategies <strategy_id>
```

## Diagnostic Script

Run the diagnostic:
```bash
cd /Users/mac/dyad-apps/openalgo
python3 scripts/diagnose_start_button_issues.py
```
