# Strategy Status Report

## 📊 Current Status: 16/19 Strategies Running

### ✅ Running Strategies (16)
Checking logs and verifying status...

### ⚠️ Not Running (3)
Identifying which strategies failed to restart...

## 🔍 Verification Steps

### 1. Check Strategy Status via API
```bash
curl -s http://127.0.0.1:5001/python/status | python3 -m json.tool
```

### 2. View Recent Logs
```bash
# List all strategy logs
ls -lht /Users/mac/dyad-apps/probable-fiesta/openalgo/log/strategies/ | head -20

# Check for errors in recent logs
tail -50 /Users/mac/dyad-apps/probable-fiesta/openalgo/log/strategies/*.log | grep -i error
```

### 3. Check Running Processes
```bash
ps aux | grep -E "strategy|mcx|nifty" | grep python | grep -v grep
```

### 4. View Strategy Logs via Web UI
- Go to: http://127.0.0.1:5001/python
- Click "Logs" button on each strategy
- Check for errors or issues

## 📋 Log Locations

Strategy logs are stored in:
- `/Users/mac/dyad-apps/probable-fiesta/openalgo/log/strategies/`

Recent log files found:
- `advanced_equity_strategy_*.log`
- `mcx_advanced_strategy_*.log`
- `trend_pullback_strategy_*.log`
- `orb_strategy_*.log`
- `delta_neutral_iron_condor_nifty_*.log`
- `mcx_ai_enhanced_strategy_*.log`

## 🔧 Troubleshooting Failed Strategies

If a strategy didn't restart:

1. **Check Logs**: View the strategy's log file for errors
2. **Verify Configuration**: Check symbol, exchange, schedule settings
3. **Check Dependencies**: Ensure all required modules are installed
4. **Restart Manually**: 
   - Go to: http://127.0.0.1:5001/python
   - Click "Start" on the failed strategy
   - Check logs again

## 📊 Monitor All Strategies

- **Web Dashboard**: http://127.0.0.1:5001/python
- **System Status**: http://127.0.0.1:5001/python/status
- **Individual Logs**: http://127.0.0.1:5001/python/logs/<strategy_id>

---

**Next Steps**: Review the logs above to identify which 3 strategies failed and why.
