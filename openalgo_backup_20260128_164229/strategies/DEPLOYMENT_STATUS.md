# Strategy Deployment Status

## Top-Ranked Strategies Deployed

Based on backtest rankings, the following strategies have been deployed:

### Rank 1 Strategies (Tied)

1. **NIFTY Greeks Enhanced** (`nifty_greeks_enhanced_20260122.py`)
   - Status: ✅ Deployed
   - Log: `logs/nifty_greeks_enhanced_20260122.log`
   - Features: Delta-based strike selection, IV Rank filtering, Theta management, Enhanced filters

2. **NIFTY Multi-Strike Momentum** (`nifty_multistrike_momentum_20260122.py`)
   - Status: ✅ Deployed
   - Log: `logs/nifty_multistrike_momentum_20260122.log`
   - Features: Dynamic strike selection, Strike laddering, Volume-weighted selection

## Deployment Commands

### Check Status
```bash
ps aux | grep -E "nifty_greeks_enhanced|nifty_multistrike" | grep python3
```

### View Logs
```bash
# NIFTY Greeks Enhanced
tail -f openalgo/strategies/logs/nifty_greeks_enhanced_20260122.log

# NIFTY Multi-Strike Momentum
tail -f openalgo/strategies/logs/nifty_multistrike_momentum_20260122.log
```

### Stop Strategies
```bash
pkill -f nifty_greeks_enhanced_20260122.py
pkill -f nifty_multistrike_momentum_20260122.py
```

### Redeploy
```bash
cd openalgo/strategies
bash scripts/deploy_ranked_strategies.sh
```

## Backtest Results Summary

- **Period Tested**: Aug 15 - Oct 31, 2025
- **Initial Capital**: ₹1,000,000
- **Strategies Tested**: 2
- **Top Performers**: Both strategies tied at rank 1

## Notes

- Strategies run continuously and check market conditions
- They will only trade during market hours (9:15 AM - 3:30 PM IST)
- Logs are written to the `logs/` directory
- Strategies use AITRAPP-enhanced risk management and exit logic
