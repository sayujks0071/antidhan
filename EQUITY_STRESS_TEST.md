# Equity Curve Stress Test Report

**Date**: 2026-02-17
**Scenario**: Crash (Simulated High Volatility Down Trend)

## Portfolio Performance
- **Total Return**: -2000173.70
- **Worst Day**: 2026-02-15 (PnL: -110.04)
- **Max Drawdown**: -0.03% on 2026-02-15

## Strategy Performance
| Strategy | Trades | Win Rate | Profit Factor | Total Return |
|----------|--------|----------|---------------|--------------|
| SuperTrendVWAP | 0 | 0.00% | 0.00 | 0.00 |
| AIHybrid | 0 | 0.00% | 0.00 | 0.00 |
| MCXMomentum | 31 | 35.48% | 0.57 | -174.00 |

## Root Cause Analysis (Worst Day)
On 2026-02-15, the portfolio lost -110.04.
Breakdown:
- **SuperTrendVWAP**: N/A
- **AIHybrid**: N/A
- **MCXMomentum**: -110.04

### Recommendations
1. **Adaptive Sizing**: Ensure strategies reduce size during high volatility (VIX > 25).
2. **Correlation**: Diversify across non-correlated assets (e.g., Gold/Silver during Equity Crash).
3. **Circuit Breakers**: Implement daily loss limits (e.g., stop trading if Portfolio DD > 2%).
