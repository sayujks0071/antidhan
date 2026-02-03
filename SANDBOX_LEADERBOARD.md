# SANDBOX LEADERBOARD (2026-02-02)

| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Status |
|------|----------|---------------|--------------|----------|--------|
| -    | SuperTrend VWAP | N/A | N/A | N/A | No Trades (Data Unavailable) |
| -    | Advanced ML Momentum | N/A | N/A | N/A | No Trades (Data Unavailable) |

## Analysis & Improvements

### SuperTrend VWAP
* **Win Rate**: N/A (< 40% threshold triggered for analysis).
* **Issue**: The strategy failed to execute any trades because the `fetch_history` call returned 0 rows ("Insufficient data"). This suggests the default 5-day lookback is insufficient when data gaps exist or the Sandbox is cold. Additionally, Sector Correlation check failures were observed in logs.
* **Action**: Improve data resilience by increasing lookback period and making sector filter optional/robust on failure.

### Advanced ML Momentum
* **Win Rate**: N/A.
* **Issue**: Failed to execute due to shared data availability issues.
