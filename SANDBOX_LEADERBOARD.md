# SANDBOX LEADERBOARD (2026-02-08)

| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |
|------|----------|---------------|--------------|----------|--------------|
| 1 | AdvancedMLMomentum | 9.08 | -52.00 | 80.0% | 5 |
| 2 | SuperTrendVWAP | 3.57 | -282.00 | 80.0% | 10 |
| 3 | GapFadeStrategy | 0.37 | -766.00 | 30.0% | 10 |

## Analysis & Improvements

### GapFadeStrategy
- **Win Rate**: 30.0% (< 40%)
- **Suggestion**: The strategy is likely fading "Breakaway Gaps" (strong trend initiations) which leads to losses. Adding an RSI filter to confirm Mean Reversion setup (Fade only if Overbought/Oversold) should improve the win rate.
