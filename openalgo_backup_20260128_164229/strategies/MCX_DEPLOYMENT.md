# MCX Deployment - Evening Session

## Status: ✅ Deployed

Switched from NSE to MCX for evening trading session.

## Deployed Strategy

**MCX Commodity Momentum Strategy** (`mcx_commodity_momentum_strategy.py`)
- Status: ✅ Running
- Log: `logs/mcx_commodity_momentum.log`

## Trading Commodities

1. **Gold** (GOLD05FEB26FUT)
2. **Silver Mini** (SILVERM27FEB26FUT)
3. **Crude Oil** (CRUDEOIL19FEB26FUT)
4. **Natural Gas** (NATURALGAS24FEB26FUT)
5. **Copper** (COPPER27FEB26FUT)

## MCX Trading Hours

- **Morning Session**: 9:00 AM - 5:00 PM IST
- **Evening Session**: 5:00 PM - 11:30 PM IST ⬅️ **CURRENT**

## Strategy Features

- Multi-indicator momentum scoring
- Volatility-based position sizing
- ATR-based stop loss and targets
- Session-aware trading
- Commodity-specific parameters
- Trend + Mean Reversion hybrid approach

## Monitoring

```bash
# View live logs
tail -f logs/mcx_commodity_momentum.log

# Check if running
ps aux | grep mcx_commodity_momentum_strategy.py | grep python3
```

## Stop Strategy

```bash
pkill -f mcx_commodity_momentum_strategy.py
```

## Notes

- Strategy scans all 5 commodities continuously
- Enters positions when momentum score > 50/100
- Max 3 positions simultaneously
- Risk per trade: 1.5% of account
- TP1: 1.5R (exit 40%), TP2: 2.5R (exit 30%), TP3: 4.0R (exit 30%)
- Trailing stop activates after TP2
