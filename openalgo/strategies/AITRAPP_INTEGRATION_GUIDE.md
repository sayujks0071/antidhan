# AITRAPP Tools Integration Guide

## Overview

The AITRAPP repository (https://github.com/sayujks0071/AITRAPP) contains production-grade trading tools and strategies that can significantly enhance our OpenAlgo strategies.

## Key Improvements Available

### 1. **Better Risk Management** (`packages/core/risk.py`)

**Current OpenAlgo Approach:**
```python
def position_size(option_ltp, lotsize):
    risk_amount = ACCOUNT_SIZE * (RISK_PCT / 100)
    risk_per_lot = option_ltp * lotsize * SL_PCT
    lots = math.floor(risk_amount / risk_per_lot) if risk_per_lot > 0 else 0
    return max(lots, 1)
```

**AITRAPP Approach (Better):**
- Portfolio heat tracking (aggregate risk across all positions)
- Freeze quantity validation
- Margin estimation
- Daily loss limit enforcement
- Better lot size handling

**Key Features:**
- `PortfolioRisk` class tracks total portfolio exposure
- `RiskManager.check_signal()` validates before entry
- `calculate_position_size()` with proper lot rounding
- Heat limit: Max 2.0% of capital at risk simultaneously

### 2. **Advanced Exit Management** (`packages/core/exits.py`)

**AITRAPP provides 6 exit types:**

1. **Hard Stop Loss**: Distance-based stop
2. **Trailing Stop**: ATR-based trailing (upward only)
3. **Take Profit Levels**: TP1 (50% partial) + TP2 (full)
4. **Time Stop**: Exit if no progress after N minutes
5. **Volatility Stop**: Exit on ATR spike (2x baseline)
6. **MAE Stop**: Maximum Adverse Excursion limit

**Additional Features:**
- Move stop to breakeven after TP1
- EOD auto square-off (15:25 IST)
- Exit urgency levels (NORMAL | URGENT)

### 3. **Better Options Strategy** (`packages/core/strategies/options_ranker.py`)

**Key Improvements:**
- **IV Percentile Filtering**: Only trade when IV rank 30-70%
- **Liquidity Scoring**: Bid-ask spread, OI, volume analysis
- **Spread Types**: Debit spreads (low IV), Credit spreads (high IV)
- **Better Strike Selection**: Based on IV regime and liquidity

**Configuration:**
```yaml
strategy_type: debit_spread  # debit_spread, credit_spread, directional
min_iv_rank: 30
max_iv_rank: 70
min_delta: 0.30
max_delta: 0.50
rr_min: 2.5
```

### 4. **Optimized Indicators** (`packages/core/indicators.py`)

**Performance Improvements:**
- TR (True Range) calculated once, reused for ATR, ADX, Supertrend
- Fast rolling mean using NumPy convolution
- All indicators computed in single pass

**Available Indicators:**
- VWAP, ATR, RSI, ADX
- EMA (fast/slow)
- Supertrend
- Bollinger Bands
- Donchian Channels
- OBV

### 5. **Strategy Base Class** (`packages/core/strategies/base.py`)

**Clean Interface:**
```python
class Strategy(ABC):
    def generate_signals(self, context: StrategyContext) -> List[Signal]
    def validate(self, context: StrategyContext) -> bool
```

**Benefits:**
- Consistent signal format
- Built-in position tracking
- Performance metrics
- Validation framework

## Integration Recommendations

### Immediate Improvements (Low Effort, High Impact)

1. **Adopt AITRAPP Position Sizing Logic**
   - Better lot size handling
   - Portfolio heat tracking
   - Freeze quantity checks

2. **Enhance Exit Management**
   - Add volatility stop (ATR spike detection)
   - Add MAE stop (maximum adverse excursion)
   - Move stop to breakeven after TP1

3. **Use AITRAPP Indicators**
   - Optimized calculations
   - Single-pass computation
   - Better performance

### Medium-Term Improvements

1. **Port AITRAPP Options Ranker Strategy**
   - Better IV percentile handling
   - Liquidity scoring
   - Spread strategy logic

2. **Implement Portfolio Heat Tracking**
   - Aggregate risk across all strategies
   - Prevent over-leveraging
   - Better capital allocation

3. **Add Exit Manager**
   - Centralized exit logic
   - Multiple exit types
   - Better position management

### Long-Term Improvements

1. **Adopt Full AITRAPP Framework**
   - Strategy base class
   - Signal ranking engine
   - OCO manager
   - Order watcher

2. **Integrate Risk Manager**
   - Full portfolio risk tracking
   - Daily loss limits
   - Margin validation

## Quick Wins for Current Strategies

### For Greeks-Enhanced Strategy:

```python
# Add volatility stop
baseline_atr = atr(df, ATR_PERIOD).iloc[-20:].mean()
current_atr = atr(df, ATR_PERIOD).iloc[-1]
if current_atr > baseline_atr * 2.0:
    # Exit position - volatility spike
    place_order(sym, OPTIONS_EXCHANGE, "SELL", pos["quantity"])
```

### For All Strategies:

```python
# Add MAE (Maximum Adverse Excursion) stop
if pos.get("max_adverse", 0) > ACCOUNT_SIZE * 0.015:  # 1.5% of account
    # Exit - too much adverse movement
    place_order(sym, OPTIONS_EXCHANGE, "SELL", pos["quantity"])

# Track MAE
current_loss = (ltp - pos["entry"]) * pos["quantity"]
if current_loss < pos.get("max_adverse", 0):
    pos["max_adverse"] = current_loss
```

### Better Position Sizing:

```python
# AITRAPP-style position sizing
def calculate_position_size_aitrapp(option_ltp, lotsize, stop_distance, net_liquid, risk_pct=0.5):
    """Better position sizing with lot handling"""
    risk_amount = net_liquid * (risk_pct / 100)
    quantity = risk_amount / stop_distance
    
    # Round to lot size
    lots = int(quantity / lotsize)
    lots = max(1, lots)  # At least 1 lot
    
    # Apply max position multiplier
    max_lots = 3  # Max 3 lots
    lots = min(lots, max_lots)
    
    return lots * lotsize
```

## AITRAPP Strategy Patterns

### ORB Strategy Pattern:
- Opening range calculation (15 min)
- Breakout confirmation (3 ticks)
- Risk-reward minimum 1.8:1

### Trend Pullback Pattern:
- EMA 34/89 trend identification
- ATR-based pullback zones
- ADX for trend strength
- Risk-reward minimum 2.0:1

### Options Ranker Pattern:
- IV percentile filtering (30-70%)
- Liquidity scoring
- Delta-based strike selection
- Spread strategy support

## Next Steps

1. **Review AITRAPP code** in `AITRAPP/AITRAPP/packages/core/`
2. **Identify specific improvements** for each strategy
3. **Create enhanced versions** using AITRAPP patterns
4. **Test and compare** performance
5. **Gradually migrate** best practices

## Key Files to Study

- `AITRAPP/AITRAPP/packages/core/risk.py` - Risk management
- `AITRAPP/AITRAPP/packages/core/exits.py` - Exit management
- `AITRAPP/AITRAPP/packages/core/strategies/options_ranker.py` - Options strategy
- `AITRAPP/AITRAPP/packages/core/indicators.py` - Technical indicators
- `AITRAPP/AITRAPP/packages/core/strategies/base.py` - Strategy framework

## Benefits Summary

✅ **Better Risk Management**: Portfolio heat, freeze quantities, margin checks
✅ **Advanced Exits**: 6 exit types, breakeven moves, volatility stops
✅ **Optimized Performance**: Single-pass indicators, TR reuse
✅ **Production-Grade**: Battle-tested patterns, SEBI-compliant
✅ **Extensible**: Clean interfaces, easy to extend
