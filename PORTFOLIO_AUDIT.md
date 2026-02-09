# COMPLETE SYSTEM AUDIT & PORTFOLIO REBALANCING

## 1. Cross-Strategy Correlation Matrix
Correlation of active positions (1min interval):

|                |   SuperTrendVWAP |   TrendPullback |   ORB |
|:---------------|-----------------:|----------------:|------:|
| SuperTrendVWAP |             1    |           -0.99 | -0.99 |
| TrendPullback  |            -0.99 |            1    |  1    |
| ORB            |            -0.99 |            1    |  1    |

**High Correlation Warnings (> 0.7):**
- **SuperTrendVWAP** vs **TrendPullback**: -0.99
  - Recommendation: Merge into 'SuperTrendVWAP' (Calmar: 6776.40 vs 3535.77)
- **SuperTrendVWAP** vs **ORB**: -0.99
  - Recommendation: Merge into 'SuperTrendVWAP' (Calmar: 6776.40 vs 2866.56)
- **TrendPullback** vs **ORB**: 1.00
  - Recommendation: Merge into 'TrendPullback' (Calmar: 3535.77 vs 2866.56)

## 2. Strategy Performance & Stress Test

| Strategy | Total PnL | Max Drawdown | Worst Day PnL | Worst Day Date | Calmar Ratio |
|----------|-----------|--------------|---------------|----------------|--------------|
| SuperTrendVWAP | 209538.52 | -7792.29 | 209538.52 | 2026-01-19 | 6776.40 |
| TrendPullback | 12728.22 | -907.16 | 12728.22 | 2026-01-19 | 3535.77 |
| ORB | 355064.21 | -31213.75 | 355064.21 | 2026-01-19 | 2866.56 |

## 3. Root Cause Analysis (Worst Day)
