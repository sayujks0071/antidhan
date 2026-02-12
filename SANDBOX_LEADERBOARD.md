# SANDBOX LEADERBOARD (2026-02-11)

| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |
|------|----------|---------------|--------------|----------|--------------|
| 1 | SuperTrendVWAP | 4.52 | 170.00 | 80.0% | 10 |
| 2 | AdvancedMLMomentum | 1.19 | 145.00 | 60.0% | 5 |
| 3 | GapFadeStrategy | 0.42 | 911.00 | 30.0% | 10 |

## Analysis & Improvements

### GapFadeStrategy
- **Win Rate**: 30.0% (< 40%)
- **Analysis**: Fading gaps without trend confirmation often leads to losses in strong momentum markets ('Gap and Go').
- **Improvement**: Add a 'Reversal Candle' check (e.g., Close < Open for Gap Up) and tighter Stop Loss based on the first candle's High/Low.
