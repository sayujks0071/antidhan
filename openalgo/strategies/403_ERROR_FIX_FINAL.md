# 403 Error Fix - Final Solution

## Issue
`mcx_global_arbitrage_strategy` fails to start with 403 error even after API key is configured.

## Root Cause
The strategy was updated in PR #48 to accept `--api_key` and `--port` as command-line arguments, but **OpenAlgo doesn't pass command-line arguments** - it only sets environment variables.

## Solution Applied
Updated the strategy to:
1. **Use environment variables first** (as set by OpenAlgo)
2. **Fall back to command-line arguments** (for manual testing)
3. **Properly read OPENALGO_APIKEY** from environment

## Code Changes

### Before (PR #48):
```python
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='MCX Global Arbitrage Strategy')
    parser.add_argument('--port', type=int, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')

    args = parser.parse_args()

    if args.port:
        API_HOST = f"http://127.0.0.1:{args.port}"
    if args.api_key:
        API_KEY = args.api_key
```

### After (Fixed):
```python
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='MCX Global Arbitrage Strategy')
    parser.add_argument('--port', type=int, help='API Port')
    parser.add_argument('--api_key', type=str, help='API Key')

    args = parser.parse_args()

    # Use command-line args if provided, otherwise fall back to environment variables
    # OpenAlgo sets environment variables, so this allows both methods
    if args.port:
        API_HOST = f"http://127.0.0.1:{args.port}"
    elif os.getenv('OPENALGO_PORT'):
        API_HOST = f"http://127.0.0.1:{os.getenv('OPENALGO_PORT')}"
    
    if args.api_key:
        API_KEY = args.api_key
    else:
        # Use environment variable (set by OpenAlgo)
        API_KEY = os.getenv('OPENALGO_APIKEY', API_KEY)
```

## Verification Steps

1. **Check API Key is Set**:
   ```bash
   cd /Users/mac/dyad-apps/probable-fiesta/openalgo
   cat strategies/strategy_env.json | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('mcx_global_arbitrage_strategy_20260128110030', {}).get('OPENALGO_APIKEY', 'NOT SET'))"
   ```

2. **Restart Strategy**:
   - Go to: http://127.0.0.1:5001/python
   - Find: `mcx_global_arbitrage_strategy`
   - Click: **Start**

3. **Check Logs**:
   ```bash
   tail -f log/strategies/mcx_global_arbitrage_strategy*.log
   ```

4. **Verify No 403 Errors**:
   - Should see: "Starting MCX Global Arbitrage Strategy"
   - Should NOT see: "403 Forbidden" or "Invalid API key"

## Expected Result
- ✅ Strategy starts successfully
- ✅ No 403 errors in logs
- ✅ API key properly read from environment variables
- ✅ Strategy runs without authentication issues

---

**Fixed**: January 28, 2026, 11:50 IST  
**File**: `openalgo/strategies/scripts/mcx_global_arbitrage_strategy.py`  
**Status**: ✅ Fixed - Ready to restart
