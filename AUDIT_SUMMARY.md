# System Audit Report (Simulated)

Date: 2026-02-23

## 1. Cross-Strategy Correlation

### Correlation Matrix
|                               |   MCXSmartStrategy |   NSERsiMacdStrategy |   MCXStrategy |   MCXNaturalGasMomentumStrategy |
|:------------------------------|-------------------:|---------------------:|--------------:|--------------------------------:|
| MCXSmartStrategy              |           1        |             0.1215   |      0.589314 |                        0.497748 |
| NSERsiMacdStrategy            |           0.1215   |             1        |     -0.295302 |                       -0.335466 |
| MCXStrategy                   |           0.589314 |            -0.295302 |      1        |                        0.601384 |
| MCXNaturalGasMomentumStrategy |           0.497748 |            -0.335466 |      0.601384 |                        1        |

### High Correlation Alerts (> 0.7)
None detected.

## 2. Equity Curve Stress Test

- **Worst Day (Simulated):** 2026-01-29
- **Max Drawdown (Simulated):** -708.35

### Root Cause Analysis (Simulated)
On 2026-01-29, simulated volatility caused a drawdown.
Strategies with exposure: MCXMomentumStrategy, MCXSmartStrategy, NSERsiMacdStrategy, NSEMaCrossoverStrategy, NSEBollingerRSIStrategy, NSERsiMacdStrategyV2, MLMomentumStrategy, MCXStrategy, MCXSmartStrategyV2, MCXSilverMomentumStrategy, MCXGoldTrendStrategy, MCXNaturalGasMomentumStrategy
