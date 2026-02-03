Found 3 trade files.

## Cross-Strategy Correlation
| strategy       |       ORB |   SuperTrendVWAP |   TrendPullback |
|:---------------|----------:|-----------------:|----------------:|
| ORB            |  1        |        -0.100728 |       -0.198638 |
| SuperTrendVWAP | -0.100728 |         1        |       -0.211289 |
| TrendPullback  | -0.198638 |        -0.211289 |        1        |

## Equity Curve Analysis

### Daily PnL
| date       |    pnl |
|:-----------|-------:|
| 2026-01-19 | 577331 |

**Worst Day**: 2026-01-19 (PnL: 577330.95)
**Max Drawdown**: 0.00

## Strategy Performance
| Strategy       |   Total PnL |   Win Rate (%) |   Max Drawdown |   Calmar Ratio |
|:---------------|------------:|---------------:|---------------:|---------------:|
| SuperTrendVWAP |    209539   |        75      |       -7792.29 |        26.8905 |
| ORB            |    355064   |        73.3333 |      -27431    |        12.9439 |
| TrendPullback  |     12728.2 |        54.1667 |       -1119.26 |        11.372  |

## Root Cause Analysis (2026-01-19)
- **Issue**: High Drawdown in ORB Strategy (-27k).
- **Observation**: Multiple conflicting trades (Long and Short) were executed on NIFTY within milliseconds (e.g., around 16:08:38).
- **Root Cause**: Signal Flickering or lack of 'debounce' logic. The strategy reacted to intra-candle noise.
- **Recommendation**: Implement candle-close confirmation or a cooldown period (already present in RiskManager but maybe not triggered if signals are simultaneous).
