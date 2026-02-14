# SANDBOX LEADERBOARD (2026-02-14)

| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |
|------|----------|---------------|--------------|----------|--------------|
| 1 | AdvancedMLMomentum | 1.66 | -241.00 | 60.0% | 5 |
| 2 | SuperTrendVWAP | 0.91 | -489.00 | 50.0% | 10 |
| 3 | GapFadeStrategy | 0.35 | -895.00 | 30.0% | 10 |

## Improvement Suggestions

### GapFadeStrategy
- **Win Rate**: 30.0% (< 40%)
- **Suggestion**: Logic Error: Uses `df.iloc[-1]` for `prev_close` which is likely Today's Close during market hours, resulting in 0 gap. Also, fixed 0.5% SL is too tight. Recommending ATR-based SL and explicit date check for Previous Close.
