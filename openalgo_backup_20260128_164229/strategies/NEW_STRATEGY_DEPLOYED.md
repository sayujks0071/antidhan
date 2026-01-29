# New Strategy Deployed: MCX Global Arbitrage

## ✅ Merge & Deployment Complete

### Strategy Details
- **Name**: MCX Global Arbitrage Strategy
- **File**: `mcx_global_arbitrage_strategy.py`
- **Strategy ID**: `mcx_global_arbitrage_strategy_20260128110030`
- **Status**: ✅ Merged and Deployed

### Strategy Description
This strategy implements global arbitrage trading by:
- Comparing MCX prices with global commodity prices
- Detecting price divergences (>3% threshold)
- Entering positions when arbitrage opportunities exist
- Exiting when prices converge (<0.5% threshold)

### Strategy Parameters
- **Divergence Threshold**: 3.0% (entry signal)
- **Convergence Threshold**: 0.5% (exit signal)
- **Lookback Period**: 20 periods

## 🚀 Start the Strategy

### Option 1: Via Web UI (Recommended)
1. Open: http://127.0.0.1:5001/python
2. Find: **MCX Global Arbitrage Strategy**
3. Configure:
   - **Symbol**: Set MCX symbol (e.g., `NATURALGAS24FEB26FUT`)
   - **Global Symbol**: Set corresponding global symbol
   - **Schedule**: Set trading hours
4. Click **"Start"** button

### Option 2: Via API
```bash
cd /Users/mac/dyad-apps/probable-fiesta/openalgo
export OPENALGO_USERNAME="sayujks0071"
export OPENALGO_PASSWORD="Apollo@20417"
python3 scripts/start_live_trading.py
# Then select the strategy ID: mcx_global_arbitrage_strategy_20260128110030
```

## 📋 Configuration Required

Before starting, configure:
1. **SYMBOL**: MCX commodity symbol (currently `REPLACE_ME`)
2. **GLOBAL_SYMBOL**: Global market symbol (currently `REPLACE_ME_GLOBAL`)
3. **Trading Schedule**: Set appropriate market hours
4. **Risk Parameters**: Review and adjust if needed

## 📊 Monitor Strategy

- **Logs**: http://127.0.0.1:5001/python/logs/mcx_global_arbitrage_strategy_20260128110030
- **Status**: http://127.0.0.1:5001/python
- **Dashboard**: http://127.0.0.1:5001/dashboard

## 🔍 Verify Deployment

```bash
# Check if strategy is in config
grep "mcx_global_arbitrage" /Users/mac/dyad-apps/probable-fiesta/openalgo/strategies/strategy_configs.json

# Check if file exists
ls -la /Users/mac/dyad-apps/probable-fiesta/openalgo/strategies/scripts/mcx_global_arbitrage_strategy.py
```

## 📝 Next Steps

1. ✅ Strategy merged from pull request
2. ✅ Strategy deployed to OpenAlgo
3. ⚠️ **Configure symbols** (SYMBOL and GLOBAL_SYMBOL)
4. ⚠️ **Set trading schedule**
5. 🚀 **Start the strategy** via web UI

---

**Deployment Time**: January 28, 2026, 11:00 IST
**Strategy ID**: `mcx_global_arbitrage_strategy_20260128110030`
