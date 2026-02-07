# SANDBOX LEADERBOARD (2026-02-07)

| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |
|------|----------|---------------|--------------|----------|--------------|
| 1 | AdvancedMLMomentum | Inf | 0.00 | 100.0% | 5 |
| 2 | SuperTrendVWAP | 1.31 | -283.00 | 50.0% | 10 |
| 3 | GapFadeStrategy | 0.43 | -707.00 | 30.0% | 10 |

## Analysis & Improvements

### GapFadeStrategy
- **Win Rate**: 30.0% (< 40%)
- **Suggestion**: Added RSI filter to confirm mean reversion (RSI > 70 for Short, RSI < 30 for Long) to avoid fading strong trends.
