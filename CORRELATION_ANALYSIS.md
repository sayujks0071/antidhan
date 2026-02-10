# Cross-Strategy Correlation Analysis

## Correlation Matrix

|                |   SuperTrendVWAP |   TrendPullback |   ORB |
|:---------------|-----------------:|----------------:|------:|
| SuperTrendVWAP |                1 |              -1 |    -1 |
| TrendPullback  |               -1 |               1 |     1 |
| ORB            |               -1 |               1 |     1 |

## Analysis
- **High Correlation (-1.00)**: SuperTrendVWAP vs TrendPullback
- **High Correlation (-1.00)**: SuperTrendVWAP vs ORB
- **High Correlation (1.00)**: TrendPullback vs ORB

## Recommendations
- Consider merging **SuperTrendVWAP** and **TrendPullback** or disabling one.
- Consider merging **SuperTrendVWAP** and **ORB** or disabling one.
- Consider merging **TrendPullback** and **ORB** or disabling one.
