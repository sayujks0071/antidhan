# Strategy Instrument Analysis Report
**Generated**: January 29, 2026  
**Subagent**: kite-openalgo-log-strategy-monitor

---

## Executive Summary

**Issue**: Only GOLD (GOLDM05FEB26FUT) is trading. Other instruments (Crude Oil, Natural Gas) are not trading due to **incorrect symbol names** in strategy configurations.

---

## Findings

### ✅ Currently Trading: GOLD

| Symbol | Current Price | Status | Strategy |
|--------|--------------|--------|----------|
| **GOLDM05FEB26FUT** | ₹180,148 | ✅ **ACTIVE** | Multiple MCX strategies |

**Current Indicators** (from last quote):
- **LTP**: ₹180,148
- **Bid**: ₹180,037 | **Ask**: ₹180,142
- **High**: ₹182,130 | **Low**: ₹168,000
- **OI**: 29,190 | **Volume**: 42,619
- **Prev Close**: ₹167,092

**Recent Activity**:
- 6 completed round-trip trades today
- P&L: ₹9,260 (realized)
- All orders tagged with "openalgo"

---

### ❌ Not Trading: CRUDE OIL

| Strategy | Configured Symbol | Correct Symbol | Status |
|----------|-------------------|----------------|--------|
| `crude_oil_clawdbot_strategy.py` | `CRUDEOILM27FEB26FUT` ❌ | `CRUDEOIL19FEB26FUT` ✅ | **SYMBOL ERROR** |
| `crude_oil_enhanced_strategy.py` | `CRUDEOILM27FEB26FUT` ❌ | `CRUDEOIL19FEB26FUT` ✅ | **SYMBOL ERROR** |

**Error**: 
```
HTTP 400: Symbol 'CRUDEOILM27FEB26FUT' not found for exchange 'MCX'
```

**Available Crude Oil Symbols**:
- `CRUDEOIL19FEB26FUT` (expiry: 19-FEB-26) ✅ **USE THIS**
- `CRUDEOIL19MAR26FUT` (expiry: 19-MAR-26)
- `CRUDEOIL20APR26FUT` (expiry: 20-APR-26)

**Current Quote** (if using correct symbol):
- Need to fetch with correct symbol

---

### ⚠️ Partially Working: NATURAL GAS

| Strategy | Configured Symbol | Status |
|----------|-------------------|--------|
| `natural_gas_clawdbot_strategy.py` | `NATURALGAS24FEB26FUT` | ⚠️ **SYMBOL EXISTS BUT NO TRADES** |

**Current Quote**:
- **LTP**: ₹356.5
- **Bid**: ₹356.5 | **Ask**: 0
- **High**: ₹356.5 | **Low**: ₹348
- **OI**: 14,801 | **Volume**: 8,750
- **Prev Close**: ₹342.8

**Issue**: Strategy is running (PID: 52494) but **no trades placed**. Possible reasons:
- Entry conditions too strict
- Indicators not meeting thresholds
- No signals generated

---

## Signals & Positions

### Current Positions
- **GOLD**: Flat (0 quantity) - All positions closed
- **Crude Oil**: No positions (symbol error prevents trading)
- **Natural Gas**: No positions (no signals generated)

### Indicator Analysis Needed

To determine why Natural Gas isn't trading, we need to check:
1. **RSI**: Current value vs trigger levels (oversold < 30, overbought > 70)
2. **ADX**: Current value vs threshold (> 25 for trend)
3. **MACD**: Signal line crossovers
4. **Price vs EMA**: Fast/Slow/Long EMA positions
5. **Volume**: Current volume vs average
6. **VWAP**: Price position relative to VWAP

**Example Format** (what subagent should report):
```
NATURALGAS24FEB26FUT:
- Price: ₹356.5
- RSI: [value] (trigger: < 30 for LONG, > 70 for SHORT)
- ADX: [value] (trigger: > 25 for trend)
- MACD: [signal] (trigger: crossover)
- Price vs 20 EMA: [above/below] (trigger: cross)
- Volume ratio: [value] (trigger: > 1.2x)
- VWAP: [value] (trigger: price cross)
```

---

## Recommendations

### 1. Fix Crude Oil Symbol (URGENT)

**Action**: Update strategy files to use correct symbol

```bash
# Find and replace in strategy files
sed -i '' 's/CRUDEOILM27FEB26FUT/CRUDEOIL19FEB26FUT/g' \
  openalgo/strategies/scripts/crude_oil_clawdbot_strategy.py \
  openalgo/strategies/scripts/crude_oil_enhanced_strategy.py
```

**Or set environment variable**:
```bash
export SYMBOL=CRUDEOIL19FEB26FUT
```

### 2. Investigate Natural Gas Strategy

**Action**: Check why no signals are generated
- Review strategy logs for entry condition failures
- Check if indicators are calculated correctly
- Verify entry thresholds aren't too strict
- Check if market hours are correct

### 3. Monitor Indicator Levels

**Action**: Use subagent to continuously monitor:
- Current indicator values (RSI, ADX, MACD, EMA, VWAP)
- Distance to trigger thresholds
- Signal generation status
- Position deployment readiness

---

## Next Checks

1. ✅ **Verify symbol corrections** - Confirm crude oil strategies use `CRUDEOIL19FEB26FUT`
2. ✅ **Fetch indicator data** - Get RSI, ADX, MACD for Natural Gas
3. ✅ **Check strategy logs** - Review why Natural Gas isn't generating signals
4. ✅ **Monitor trigger proximity** - Report how close indicators are to entry thresholds
5. ✅ **Test corrected strategies** - Restart crude oil strategies with correct symbols

---

## Running Strategies Status

| Strategy | PID | Symbol | Status |
|----------|-----|--------|--------|
| mcx_clawdbot_strategy | 52447 | GOLDM05FEB26FUT | ✅ Trading |
| mcx_quantum_strategy | 52444 | GOLDM05FEB26FUT | ✅ Trading |
| mcx_elite_strategy | 52433 | GOLDM05FEB26FUT | ✅ Trading |
| mcx_advanced_momentum_strategy | 52445 | GOLDM05FEB26FUT | ✅ Trading |
| mcx_neural_strategy | 52443 | GOLDM05FEB26FUT | ✅ Trading |
| mcx_ai_enhanced_strategy | 52428 | GOLDM05FEB26FUT | ✅ Trading |
| crude_oil_clawdbot_strategy | 52469 | ❌ Wrong symbol | ⚠️ Error |
| crude_oil_enhanced_strategy | 52493 | ❌ Wrong symbol | ⚠️ Error |
| natural_gas_clawdbot_strategy | 52494 | NATURALGAS24FEB26FUT | ⚠️ No signals |

---

**Report Generated by**: kite-openalgo-log-strategy-monitor subagent
