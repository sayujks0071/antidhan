# Trade Monitoring Fixes - January 29, 2026

## Summary
Fixed critical issues identified during real-time trade monitoring that were preventing strategies from executing trades.

## Issues Fixed

### 1. ✅ MCX Global Arbitrage Strategy - Symbol Configuration
**Problem**: Strategy had hardcoded `SYMBOL = "REPLACE_ME"` and didn't accept command-line arguments for symbols.

**Fix**:
- Added `--symbol` and `--global_symbol` command-line arguments
- Added environment variable support (`SYMBOL`, `GLOBAL_SYMBOL`)
- Added validation to prevent running with "REPLACE_ME"
- Default symbols: `GOLDM05FEB26FUT` (MCX) and `GOLD_GLOBAL` (Global)

**File**: `openalgo/strategies/scripts/mcx_global_arbitrage_strategy.py`

### 2. ✅ MCX Commodity Momentum Strategy - Symbol Configuration
**Problem**: Strategy had hardcoded `SYMBOL = "REPLACE_ME"` without argument parsing.

**Fix**:
- Added `--symbol` command-line argument
- Added environment variable support (`SYMBOL`)
- Added validation to prevent running with "REPLACE_ME"
- Default symbol: `GOLDM05FEB26FUT`

**File**: `openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py`

### 3. ✅ MCX Advanced Momentum Strategy - Error Handling
**Problem**: "No timeframe signals available" warnings provided no diagnostic information.

**Fix**:
- Enhanced error messages to explain possible causes:
  - Insufficient historical data
  - API connectivity issues
  - Symbol not found in master contracts
  - Market data not available
- Added detailed error logging in `analyze_multi_timeframe` function

**File**: `openalgo/strategies/scripts/mcx_advanced_momentum_strategy.py`

### 4. ✅ NIFTY Strategies - Symbol Normalization
**Problem**: Strategies were receiving symbols like "NIFTY50", "NIFTYBANK", "NIFTY 50" which don't match master contract formats.

**Fix**: Added symbol normalization at strategy startup:
- `NIFTY50` → `NIFTY`
- `NIFTY 50` → `NIFTY`
- `NIFTYBANK` → `BANKNIFTY`
- `NIFTY BANK` → `BANKNIFTY`

**Files Fixed**:
- `openalgo/strategies/scripts/advanced_ml_momentum_strategy.py`
- `openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py`
- `openalgo/strategies/scripts/supertrend_vwap_strategy.py`

## Next Steps

### 1. Restart Strategies with Proper Symbols

**MCX Global Arbitrage**:
```bash
# Stop existing process
pkill -f "mcx_global_arbitrage_strategy.py"

# Restart with proper symbol
cd /Users/mac/dyad-apps/probable-fiesta/openalgo/strategies/scripts
python3 mcx_global_arbitrage_strategy.py \
  --symbol GOLDM05FEB26FUT \
  --global_symbol GOLD_GLOBAL \
  --port 5001 \
  --api_key f8ef87416d80ec3785f715a14ed966516887daaede32acf9d75164b5e9f82bf3
```

**MCX Commodity Momentum**:
```bash
# Stop existing process
pkill -f "mcx_commodity_momentum_strategy.py"

# Restart with proper symbol
python3 mcx_commodity_momentum_strategy.py \
  --symbol GOLDM05FEB26FUT \
  --port 5001 \
  --api_key f8ef87416d80ec3785f715a14ed966516887daaede32acf9d75164b5e9f82bf3
```

**NIFTY Strategies** (will auto-normalize symbols):
```bash
# Advanced ML Momentum
python3 advanced_ml_momentum_strategy.py \
  --symbol NIFTY \
  --port 5001 \
  --api_key f8ef87416d80ec3785f715a14ed966516887daaede32acf9d75164b5e9f82bf3

# AI Hybrid Reversion Breakout
python3 ai_hybrid_reversion_breakout.py \
  --symbol NIFTY \
  --port 5001 \
  --api_key f8ef87416d80ec3785f715a14ed966516887daaede32acf9d75164b5e9f82bf3

# SuperTrend VWAP
python3 supertrend_vwap_strategy.py \
  --symbol BANKNIFTY \
  --quantity 10 \
  --api_key f8ef87416d80ec3785f715a14ed966516887daaede32acf9d75164b5e9f82bf3 \
  --host http://127.0.0.1:5001
```

### 2. Verify Master Contracts

Ensure NSE_INDEX symbols are in master contracts:
```bash
# Check if NIFTY and BANKNIFTY are available
curl http://127.0.0.1:5001/api/v1/search?symbol=NIFTY&exchange=NSE_INDEX
curl http://127.0.0.1:5001/api/v1/search?symbol=BANKNIFTY&exchange=NSE_INDEX
```

### 3. Monitor After Restart

Watch for:
- ✅ Symbols are no longer "REPLACE_ME"
- ✅ NIFTY strategies normalize symbols correctly
- ✅ MCX strategies fetch data successfully
- ✅ Trade entries/exits appear in logs

```bash
# Monitor logs
tail -f /Users/mac/dyad-apps/probable-fiesta/openalgo/log/strategies/*.log | grep -E "\[ENTRY\]|\[EXIT\]|SIGNAL|ERROR"
```

## Expected Improvements

1. **MCX Strategies**: Will now use proper symbols and can execute trades
2. **NIFTY Strategies**: Will normalize symbols correctly and find master contracts
3. **Error Messages**: More informative diagnostics for troubleshooting
4. **Trade Execution**: Strategies should start generating actual trade entries

## Testing Checklist

- [ ] MCX Global Arbitrage restarted with proper symbol
- [ ] MCX Commodity Momentum restarted with proper symbol  
- [ ] NIFTY strategies normalize symbols correctly
- [ ] No more "REPLACE_ME" in logs
- [ ] No more "Symbol not found" errors for NIFTY
- [ ] Trade entries appear in logs
- [ ] MCX Advanced Momentum provides better error messages

## Notes

- All fixes are backward compatible (default values provided)
- Strategies can still use environment variables if preferred
- Symbol normalization happens automatically for NIFTY strategies
- Validation prevents strategies from running with invalid symbols
