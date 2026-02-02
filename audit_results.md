# System Audit & Portfolio Rebalancing Report

## 1. Cross-Strategy Correlation Analysis

### Correlation Matrix (Hourly PnL)
|                |   SuperTrendVWAP |   TrendPullback |   ORB |
|:---------------|-----------------:|----------------:|------:|
| SuperTrendVWAP |                1 |               1 |     1 |
| TrendPullback  |                1 |               1 |     1 |
| ORB            |                1 |               1 |     1 |

### ⚠️ High Correlation Alerts (> 0.7)
- **SuperTrendVWAP** vs **TrendPullback**: 1.00
  - Action: Consider merging or keeping higher Calmar strategy.
- **SuperTrendVWAP** vs **ORB**: 1.00
  - Action: Consider merging or keeping higher Calmar strategy.
- **TrendPullback** vs **ORB**: 1.00
  - Action: Consider merging or keeping higher Calmar strategy.

## 2. Strategy Performance (Calmar Ratio)

|                |   Net PnL |     Max DD |   Calmar |
|:---------------|----------:|-----------:|---------:|
| SuperTrendVWAP |  209539   | -0.0430762 | 17755    |
| TrendPullback  |   12728.2 | -0.0103448 |  4490.97 |
| ORB            |  355064   | -0.101351  | 12787.1  |

## 3. Equity Curve Stress Test

### Worst Day Analysis
- **Date:** 2026-01-19
- **Net Loss:** 577330.95

#### Trades on Worst Day:
|    | strategy       | symbol    | direction   |       pnl |
|---:|:---------------|:----------|:------------|----------:|
| 44 | ORB            | FINNIFTY  | LONG        |  20361.6  |
| 45 | ORB            | FINNIFTY  | LONG        |  17247.7  |
| 46 | ORB            | NIFTY     | LONG        |  18779.7  |
| 47 | ORB            | BANKNIFTY | LONG        |  18243.5  |
| 48 | ORB            | BANKNIFTY | LONG        |  14170.1  |
| 49 | ORB            | BANKNIFTY | SHORT       |  23851.1  |
| 50 | ORB            | BANKNIFTY | LONG        |  -6980.79 |
| 51 | ORB            | NIFTY     | SHORT       | -14571.8  |
| 52 | ORB            | BANKNIFTY | SHORT       |  15761.3  |
| 53 | ORB            | FINNIFTY  | LONG        |  16522.2  |
| 54 | ORB            | NIFTY     | SHORT       |  16961.4  |
| 55 | ORB            | BANKNIFTY | SHORT       |  25145.3  |
| 56 | ORB            | BANKNIFTY | SHORT       |  12736.9  |
| 57 | ORB            | FINNIFTY  | SHORT       |  23395.4  |
| 58 | ORB            | FINNIFTY  | SHORT       |  12898    |
| 20 | TrendPullback  | RELIANCE  | LONG        |    819.01 |
| 21 | TrendPullback  | TCS       | SHORT       |   1390.31 |
| 22 | TrendPullback  | RELIANCE  | SHORT       |   -143.73 |
| 23 | TrendPullback  | ICICIBANK | LONG        |   -251.79 |
| 24 | TrendPullback  | INFY      | SHORT       |   -188.38 |
| 25 | TrendPullback  | ICICIBANK | SHORT       |    802.24 |
| 26 | TrendPullback  | TCS       | LONG        |   -180.59 |
| 27 | TrendPullback  | TCS       | SHORT       |   1388.59 |
| 28 | TrendPullback  | TCS       | LONG        |   1997.24 |
| 29 | TrendPullback  | RELIANCE  | SHORT       |   1317.47 |
| 30 | TrendPullback  | TCS       | LONG        |   -375.11 |
| 31 | TrendPullback  | HDFCBANK  | LONG        |   1620.47 |
| 59 | ORB            | NIFTY     | SHORT       |  13464.8  |
| 60 | ORB            | BANKNIFTY | LONG        | -14894    |
| 61 | ORB            | NIFTY     | SHORT       | -12537    |
| 62 | ORB            | FINNIFTY  | LONG        |  25735    |
| 63 | ORB            | FINNIFTY  | LONG        |  23109.9  |
| 64 | ORB            | BANKNIFTY | SHORT       |  17819.8  |
| 65 | ORB            | FINNIFTY  | SHORT       |  -7046.73 |
| 66 | ORB            | BANKNIFTY | SHORT       |  29776.1  |
| 67 | ORB            | BANKNIFTY | SHORT       |  22446.8  |
| 68 | ORB            | NIFTY     | SHORT       | -16319.7  |
| 69 | ORB            | FINNIFTY  | LONG        | -10420.3  |
| 70 | ORB            | NIFTY     | SHORT       |  27816.3  |
| 71 | ORB            | NIFTY     | LONG        |  24828.5  |
| 72 | ORB            | FINNIFTY  | SHORT       |  28283.5  |
| 73 | ORB            | NIFTY     | SHORT       | -11520.5  |
| 32 | TrendPullback  | ICICIBANK | LONG        |   -204.05 |
| 33 | TrendPullback  | RELIANCE  | LONG        |   -331.56 |
| 34 | TrendPullback  | TCS       | LONG        |   -514.73 |
| 35 | TrendPullback  | INFY      | LONG        |    631.55 |
| 36 | TrendPullback  | RELIANCE  | SHORT       |   -700.47 |
| 37 | TrendPullback  | ICICIBANK | LONG        |   1090.53 |
| 38 | TrendPullback  | HDFCBANK  | SHORT       |   -195.12 |
| 39 | TrendPullback  | INFY      | LONG        |    334.64 |
| 40 | TrendPullback  | HDFCBANK  | LONG        |   1744.86 |
| 41 | TrendPullback  | ICICIBANK | SHORT       |   1460.93 |
| 42 | TrendPullback  | INFY      | LONG        |   1489.2  |
| 43 | TrendPullback  | TCS       | SHORT       |   -273.29 |
|  0 | SuperTrendVWAP | NIFTY     | LONG        |   7992.91 |
|  1 | SuperTrendVWAP | TCS       | SHORT       |  16140.4  |
|  2 | SuperTrendVWAP | INFY      | LONG        |   8626.02 |
|  3 | SuperTrendVWAP | BANKNIFTY | LONG        |  -3317.78 |
|  4 | SuperTrendVWAP | TCS       | LONG        |  14596.1  |
|  5 | SuperTrendVWAP | NIFTY     | LONG        |  18215.9  |
|  6 | SuperTrendVWAP | BANKNIFTY | LONG        |   8330.73 |
|  7 | SuperTrendVWAP | RELIANCE  | SHORT       |   2325.55 |
|  8 | SuperTrendVWAP | INFY      | LONG        |   7985.69 |
|  9 | SuperTrendVWAP | BANKNIFTY | LONG        |  -7792.29 |
| 10 | SuperTrendVWAP | BANKNIFTY | SHORT       |  28644.6  |
| 11 | SuperTrendVWAP | NIFTY     | SHORT       |  25063.2  |
| 12 | SuperTrendVWAP | BANKNIFTY | SHORT       |  14911.7  |
| 13 | SuperTrendVWAP | BANKNIFTY | LONG        |  26265.8  |
| 14 | SuperTrendVWAP | TCS       | LONG        |  17494.2  |
| 15 | SuperTrendVWAP | BANKNIFTY | LONG        |  -6017.34 |
| 16 | SuperTrendVWAP | NIFTY     | LONG        |   -572.55 |
| 17 | SuperTrendVWAP | NIFTY     | LONG        |  -1152.54 |
| 18 | SuperTrendVWAP | INFY      | LONG        |  17418.8  |
| 19 | SuperTrendVWAP | TCS       | LONG        |  14379.3  |

#### Root Cause Analysis (Automated)
- **Worst Strategy:** TrendPullback (12728.22)
