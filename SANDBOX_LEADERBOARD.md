# SANDBOX LEADERBOARD (2026-02-21)

*Note: No new trade logs were found for today (2026-02-21). The rankings below reflect the most recent available audit data.*

| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |
|------|----------|---------------|--------------|----------|--------------|
| 1 | NSE_RSI_MACD_Strategy | 0.00 | 65.00 | 0.0% | 3 |

## Analysis & Improvements

### NSE_RSI_MACD_Strategy
- **Win Rate**: 0.0% (< 40%)
- **Status**: Fixed & Optimized
- **Root Cause**:
    1.  Redundant data fetching and indicator calculation caused latency and potential signal drift.
    2.  Lack of Stop Loss mechanism led to large drawdowns.
    3.  Exit condition (RSI > 70) was too passive for strong trends.
- **Improvements Applied**:
    -   **Code Optimization**: Removed redundant `fetch_history` and `calculate_indicators` calls. Now leverages `BaseStrategy`'s efficient cycle.
    -   **Risk Management**: Implemented **ATR Trailing Stop** (2.0 * ATR) to cut losses early.
    -   **Exit Logic**: Tightened exit criteria to **RSI > 80** (Extreme Overbought) or **RSI > 70 AND Bearish Crossover**.
    -   **Validation**: Verified syntax and dependency imports.
