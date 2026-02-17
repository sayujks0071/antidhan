# SANDBOX LEADERBOARD (2026-02-16)

| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |
|------|----------|---------------|--------------|----------|--------------|
| 1 | AdvancedMLMomentum | Inf | 0.00 | 100.0% | 5 |
| 2 | SuperTrendVWAP | 0.53 | -694.00 | 40.0% | 10 |
| 3 | GapFadeStrategy | 0.45 | -911.00 | 30.0% | 10 |

## Improvement Suggestions

### GapFadeStrategy
- **Win Rate**: 30.0% (< 40%)
- **Suggestion**: Strategy logic was improved in `openalgo/strategies/scripts/gap_fade_strategy.py`.
  - **Gap Threshold**: Increased from 0.5% to 0.75% to filter noise.
  - **ADX Filter**: Lowered to 25 to target weaker trends (better for fading).
  - **RSI Filter**: Added RSI confirmation (Short if RSI > 60, Long if RSI < 40).
