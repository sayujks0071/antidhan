# Action Items Required - Post Status Update

**Generated**: January 28, 2026, 12:15 IST  
**Based On**: STATUS_UPDATE_REPORT.md

---

## 🔴 CRITICAL - Immediate Action Required

### 1. Fix API Keys for 2 Strategies (403 Errors)

**Strategies**:
- `mcx_elite_strategy` (ID: `mcx_elite_strategy_20260127140511`)
- `mcx_neural_strategy` (ID: `mcx_neural_strategy_20260127145926`)

**Issue**: Using invalid API key (`630db05e...`) causing 403 FORBIDDEN errors

**Status**: ✅ **API Keys Updated** - Need to restart strategies

**Action**:
```bash
# API keys have been updated in strategy_env.json
# Now restart strategies via Web UI:
# 1. Go to: http://127.0.0.1:5001/python
# 2. Stop → Start for each strategy
```

**Expected Result**: No more 403 errors, strategies can fetch historical data

---

### 2. Restart advanced_ml_momentum_strategy (Apply PR #48)

**Status**: Currently STOPPED (needs restart to apply PR #48 changes)

**Changes to Apply**:
- RSI threshold: 55 → 50 ✅
- Volume threshold: 0.8x → 0.5x ✅

**Action**:
```bash
# Via Web UI:
# 1. Go to: http://127.0.0.1:5001/python
# 2. Find: advanced_ml_momentum_strategy
# 3. Click: Start
```

**Expected Result**: More signals generated with relaxed conditions

---

### 3. Adjust ROC Threshold (If Still No Orders)

**Issue**: ROC condition failing (getting negative values like -0.0006)

**Current Code**:
```python
if (last['roc'] > self.roc_threshold and  # threshold = 0.01 (1%)
    last['rsi'] > 50 and
    rs_excess > 0 and
    current_price > last['sma50'] and
    sentiment >= 0):
```

**Problem**: ROC is negative (-0.0006), but threshold requires > 0.01

**Options**:
1. **Lower ROC threshold** to 0.001 (0.1%) or 0.0 (accept any positive)
2. **Make ROC optional** (use OR instead of AND)
3. **Accept negative ROC** if other conditions are strong

**Action**: Monitor after restart - if still no orders, adjust ROC threshold

---

## ⚠️ MEDIUM PRIORITY

### 4. Restart Stopped Strategies

**Strategies Ready to Start**:
- `natural_gas_clawdbot_strategy` - API key configured ✅
- `crude_oil_enhanced_strategy` - API key configured ✅

**Action**: Start via Web UI when ready

---

### 5. Monitor Order Placement

**After restarting `advanced_ml_momentum_strategy`**:
- Watch logs for "Strong Momentum Signal" messages
- Verify orders are being placed
- If still no orders, adjust ROC threshold

**Monitor Command**:
```bash
tail -f log/strategies/advanced_ml_momentum_strategy*.log | grep -iE "signal|order|ROC|RSI"
```

---

## 📊 Summary of Changes Since Last Report

### ✅ Fixed
1. ✅ `mcx_global_arbitrage_strategy` - 403 error fixed, now running
2. ✅ API keys updated for `mcx_elite_strategy` and `mcx_neural_strategy`
3. ✅ PR #48 merged - Entry conditions relaxed

### ⚠️ Still Required
1. 🔴 Restart `mcx_elite_strategy` and `mcx_neural_strategy` (to apply new API keys)
2. 🔴 Restart `advanced_ml_momentum_strategy` (to apply PR #48 changes)
3. ⚠️ Monitor and potentially adjust ROC threshold

### 📈 Improvements
- **New Strategy Running**: mcx_global_arbitrage_strategy ✅
- **Signals Generated**: mcx_global_arbitrage generating arbitrage signals ✅
- **Optimization**: Still running in background ✅

---

## Quick Action Checklist

- [ ] Restart `mcx_elite_strategy` (API key fixed)
- [ ] Restart `mcx_neural_strategy` (API key fixed)
- [ ] Restart `advanced_ml_momentum_strategy` (PR #48 changes)
- [ ] Monitor `advanced_ml_momentum_strategy` logs for orders
- [ ] If no orders, adjust ROC threshold
- [ ] (Optional) Start `natural_gas_clawdbot_strategy`
- [ ] (Optional) Start `crude_oil_enhanced_strategy`

---

**Priority Order**:
1. **Fix 403 errors** (restart mcx_elite, mcx_neural)
2. **Apply PR #48** (restart advanced_ml_momentum)
3. **Monitor orders** (verify fixes working)
4. **Adjust thresholds** (if still needed)
