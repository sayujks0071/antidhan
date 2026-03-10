# SANDBOX LEADERBOARD (2026-03-10)

| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |
|------|----------|---------------|--------------|----------|--------------|
| 1 | AdvancedMLMomentum | 3.01 | 140.00 | 80.0% | 5 |
| 2 | SuperTrendVWAP | 1.45 | 189.00 | 60.0% | 10 |
| 3 | GapFadeStrategy | 0.37 | 1016.00 | 30.0% | 10 |

## Analysis & Improvements

### GapFadeStrategy
- **Win Rate**: 30.0% (< 40%)
- **Analysis**: Fading gaps without trend confirmation often leads to losses in strong momentum markets ('Gap and Go').
- **Improvement**: Add a 'Reversal Candle' check (e.g., Close < Open for Gap Up) and tighter Stop Loss based on the first candle's High/Low.
