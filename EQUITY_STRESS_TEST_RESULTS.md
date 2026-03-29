# Equity Curve Stress Test Results

## Performance Summary
- **Total PnL**: -4162.00
- **Best Day**: 2026-02-04 (+588.00)
- **Worst Day**: 2026-02-16 (-1479.00)
- **Max Drawdown**: -4628.00

## Worst Day Analysis
### Date: 2026-02-16
**Net PnL**: -1479.00

#### Strategy Breakdown on Worst Day:
- **AdvancedMLMomentum**: -157.00
- **GapFadeStrategy**: -668.00
- **SuperTrendVWAP**: -654.00

### Root Cause Analysis (Simulated)
- **GapFadeStrategy Failure**: Likely a strong trend day where gaps did not fill. The strategy faded a gap that turned into a runaway trend.
- **SuperTrendVWAP Failure**: Likely a choppy/sideways market causing false breakouts and whipsaws.
- **Systemic Market Crash**: All strategies correlated negatively. High IV crush or gap-down open suspected.

## Monthly Equity Curve Data
| Date | Daily PnL | Cumulative PnL |
|------|-----------|----------------|
| 2026-01-26 | 39.00 | 39.00 |
| 2026-01-27 | -60.00 | -21.00 |
| 2026-01-28 | 487.00 | 466.00 |
| 2026-01-29 | -586.00 | -120.00 |
| 2026-01-30 | 429.00 | 309.00 |
| 2026-02-02 | -588.00 | -279.00 |
| 2026-02-03 | -614.00 | -893.00 |
| 2026-02-04 | 588.00 | -305.00 |
| 2026-02-05 | 213.00 | -92.00 |
| 2026-02-06 | -341.00 | -433.00 |
| 2026-02-09 | -9.00 | -442.00 |
| 2026-02-10 | -358.00 | -800.00 |
| 2026-02-11 | 209.00 | -591.00 |
| 2026-02-12 | -431.00 | -1022.00 |
| 2026-02-13 | -28.00 | -1050.00 |
| 2026-02-16 | -1479.00 | -2529.00 |
| 2026-02-17 | -804.00 | -3333.00 |
| 2026-02-18 | -197.00 | -3530.00 |
| 2026-02-19 | -280.00 | -3810.00 |
| 2026-02-20 | -256.00 | -4066.00 |
| 2026-02-23 | 257.00 | -3809.00 |
| 2026-02-24 | -253.00 | -4062.00 |
| 2026-02-25 | -100.00 | -4162.00 |
