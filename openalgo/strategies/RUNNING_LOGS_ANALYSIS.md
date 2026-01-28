# Running Strategy Logs Analysis Report
**Generated**: January 28, 2026, 11:15 IST  
**Total Running Strategies**: 16

## Summary

### Overall Status
- ✅ **No Critical Errors**: Most strategies running without critical issues
- ⚠️ **Warnings Present**: Multiple strategies have warnings (mostly non-critical)
- 📊 **Signal Activity**: 2 strategies generating signals
- 🔴 **API Errors**: 2 strategies with HTTP 500 errors

## Detailed Analysis by Strategy

### 1. ✅ trend_pullback_strategy
- **PID**: 61319
- **Status**: Healthy
- **Errors**: 0
- **Warnings**: 29
- **Signals**: 0
- **Trades**: 0
- **Assessment**: Running smoothly with minor warnings

### 2. ✅ mcx_commodity_momentum_strategy
- **PID**: 61343
- **Status**: Healthy
- **Errors**: 0
- **Warnings**: 56
- **Signals**: 0
- **Trades**: 0
- **Assessment**: Normal operation

### 3. ⚠️ sector_momentum_strategy
- **PID**: 61321
- **Status**: Warning
- **Errors**: 0
- **Warnings**: 250 (High)
- **Signals**: 0
- **Trades**: 0
- **Assessment**: High warning count - investigate warnings

### 4. ✅ delta_neutral_iron_condor_nifty
- **PID**: 61341
- **Status**: Healthy
- **Errors**: 0
- **Warnings**: 2
- **Signals**: 0
- **Trades**: 0
- **Assessment**: Excellent - minimal warnings

### 5. ⚠️ supertrend_vwap_strategy
- **PID**: 61323
- **Status**: Warning
- **Errors**: 0
- **Warnings**: 172
- **Signals**: 0
- **Trades**: 0
- **Assessment**: Moderate warning count

### 6. ⚠️ orb_strategy
- **PID**: 61325
- **Status**: Warning
- **Errors**: 0
- **Warnings**: 58
- **Signals**: 0
- **Trades**: 0
- **Assessment**: Normal warnings

### 7. ⚠️ ai_hybrid_reversion_breakout
- **PID**: 61339
- **Status**: Warning
- **Errors**: 0
- **Warnings**: 100
- **Signals**: 0
- **Trades**: 0
- **Assessment**: Moderate warnings

### 8. ⚠️ advanced_ml_momentum_strategy
- **PID**: 61328
- **Status**: Warning
- **Errors**: 0
- **Warnings**: 168
- **Signals**: 0
- **Trades**: 0
- **Assessment**: Moderate warnings

### 9. 📊 multi_timeframe_momentum_strategy
- **PID**: 61337
- **Status**: Active (Generating Signals)
- **Errors**: 0
- **Warnings**: 224
- **Signals**: 56 ✅
- **Trades**: 0
- **Assessment**: **ACTIVE** - Generating signals successfully

### 10. 🔴 mcx_advanced_momentum_strategy
- **PID**: 61330
- **Status**: Issues Detected
- **Errors**: 22
- **Warnings**: 252
- **Signals**: 26 ✅
- **Trades**: 0
- **Assessment**: **ACTIVE** but has errors - needs investigation

### 11. 🔴 mcx_elite_strategy
- **PID**: 61331
- **Status**: Critical
- **Errors**: 54
- **Warnings**: 251
- **Signals**: 0
- **Trades**: 0
- **API Errors**: HTTP 500 (1)
- **Assessment**: **CRITICAL** - Multiple errors and API failures

### 12. 🔴 mcx_neural_strategy
- **PID**: 61336
- **Status**: Critical
- **Errors**: 58
- **Warnings**: 249
- **Signals**: 0
- **Trades**: 0
- **API Errors**: HTTP 500 (1)
- **Assessment**: **CRITICAL** - Multiple errors and API failures

### 13. ⚠️ mcx_quantum_strategy
- **PID**: 61332
- **Status**: Warning
- **Errors**: 33
- **Warnings**: 204
- **Signals**: 0
- **Trades**: 0
- **Assessment**: Has errors - needs attention

### 14. ✅ mcx_ai_enhanced_strategy
- **PID**: 61333
- **Status**: Healthy
- **Errors**: 0
- **Warnings**: 56
- **Signals**: 0
- **Trades**: 0
- **Assessment**: Running normally

### 15. ⚠️ mcx_clawdbot_strategy
- **PID**: 61334
- **Status**: Warning
- **Errors**: 28
- **Warnings**: 56
- **Signals**: 0
- **Trades**: 0
- **Assessment**: Has errors - investigate

### 16. ✅ crude_oil_clawdbot_strategy
- **PID**: 61335
- **Status**: Healthy
- **Errors**: 0
- **Warnings**: 28
- **Signals**: 0
- **Trades**: 0
- **Assessment**: Running smoothly

## Key Findings

### 🔴 Critical Issues (Immediate Action Required)
1. **mcx_elite_strategy**: 54 errors + HTTP 500 API error
2. **mcx_neural_strategy**: 58 errors + HTTP 500 API error

### ⚠️ Warning Issues (Investigate)
1. **sector_momentum_strategy**: 250 warnings
2. **mcx_advanced_momentum_strategy**: 22 errors + 252 warnings
3. **mcx_quantum_strategy**: 33 errors
4. **mcx_clawdbot_strategy**: 28 errors

### ✅ Healthy Strategies
- trend_pullback_strategy
- mcx_commodity_momentum_strategy
- delta_neutral_iron_condor_nifty
- mcx_ai_enhanced_strategy
- crude_oil_clawdbot_strategy

### 📊 Active Signal Generators
1. **multi_timeframe_momentum_strategy**: 56 signals
2. **mcx_advanced_momentum_strategy**: 26 signals

## Recommendations

### Immediate Actions
1. **Investigate HTTP 500 errors** in:
   - mcx_elite_strategy
   - mcx_neural_strategy
   - Check API connectivity and authentication

2. **Review error logs** for strategies with high error counts:
   - mcx_neural_strategy (58 errors)
   - mcx_elite_strategy (54 errors)
   - mcx_quantum_strategy (33 errors)

### Monitoring
1. **Monitor signal-generating strategies**:
   - multi_timeframe_momentum_strategy
   - mcx_advanced_momentum_strategy

2. **Check warning patterns** for:
   - sector_momentum_strategy (250 warnings)
   - Strategies with >100 warnings

### Clawdbot Integration
- ⚠️ Clawdbot WebSocket not available (port 18789)
- AI analysis attempted but connection failed
- To enable full AI analysis, ensure Clawdbot service is running

## Next Steps

1. **Check specific error messages** in critical strategies:
   ```bash
   cd /Users/mac/dyad-apps/probable-fiesta/openalgo
   tail -100 log/strategies/mcx_elite_strategy*.log | grep ERROR
   tail -100 log/strategies/mcx_neural_strategy*.log | grep ERROR
   ```

2. **Verify API connectivity** for strategies with HTTP 500 errors

3. **Review warning patterns** to identify common issues

4. **Monitor signal-generating strategies** for trade execution

---

**Analysis Tool**: `scripts/check_all_running_logs_clawdbot.py`  
**Clawdbot Status**: ⚠️ WebSocket connection failed (service may not be running)  
**Log Location**: `log/strategies/`
