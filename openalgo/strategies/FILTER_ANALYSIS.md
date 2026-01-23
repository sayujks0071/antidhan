# MCX Strategy Filter Analysis

## Current Filter Settings

### Entry Threshold
- **MIN_ENTRY_SCORE**: 50/100
- **HIGH_CONVICTION**: 70/100

### Position Limits
- **MAX_POSITIONS**: 3
- **RISK_PER_TRADE_PCT**: 1.5%

### Time Filters
- **AVOID_FIRST_MINUTES**: 15 minutes after session start
- **AVOID_LAST_MINUTES**: 10 minutes before session end

## Analysis from Logs

### Observed Signal Scores
- **Long scores**: Typically 20-45 (below threshold)
- **Short scores**: Typically 15-38 (below threshold)
- **Highest observed**: ~45 (still below 50 threshold)

### Issue Identified
**Filter is too stringent** - Signals are being generated (Long=40-45) but not entering trades because they don't meet the 50 threshold.

### Recommendations

1. **Lower MIN_ENTRY_SCORE** from 50 to 40 or 35
   - This would allow more trades while still maintaining quality
   - Current signals (40-45) would qualify

2. **Adjust scoring weights** to give more weight to strong indicators
   - Current SuperTrend is 20% - could increase to 25%
   - ADX is 15% - could increase to 20% when ADX > 50

3. **Add dynamic threshold** based on market conditions
   - Lower threshold during high volatility
   - Higher threshold during low volatility

4. **Review ADX_THRESHOLD** (currently 25)
   - Some commodities showing ADX > 70 but still not entering
   - Consider lowering to 20 or making it advisory only

## Suggested Changes

```python
# More lenient entry
MIN_ENTRY_SCORE = 40  # Lowered from 50

# Or dynamic based on ADX
if current_adx > 50:
    MIN_ENTRY_SCORE = 35  # Strong trend, lower threshold
else:
    MIN_ENTRY_SCORE = 45  # Weak trend, higher threshold
```
