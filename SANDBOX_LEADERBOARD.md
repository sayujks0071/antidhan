# SANDBOX LEADERBOARD (2026-03-01)

| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |
|------|----------|---------------|--------------|----------|--------------|
| 1 | SuperTrendVWAP | 9.32 | 130.00 | 90.0% | 10 |
| 2 | AdvancedMLMomentum | 0.89 | 272.00 | 60.0% | 5 |
| 3 | GapFadeStrategy | 0.50 | 796.00 | 30.0% | 10 |

## Analysis & Improvements

### GapFadeStrategy
- **Win Rate**: 30.0% (< 40%)
- **Analysis**: Fading gaps without trend confirmation often leads to losses in strong momentum markets ('Gap and Go').
- **Improvement**: Add a 'Reversal Candle' check (e.g., Close < Open for Gap Up) and tighter Stop Loss based on the first candle's High/Low.
