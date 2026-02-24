# SANDBOX LEADERBOARD (2026-02-24)

| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |
|------|----------|---------------|--------------|----------|--------------|
| 1 | AdvancedMLMomentum | 1.11 | 274.00 | 60.0% | 5 |
| 2 | SuperTrendVWAP | 0.70 | 480.00 | 40.0% | 10 |
| 3 | GapFadeStrategy | 0.54 | 784.00 | 30.0% | 10 |

## Analysis & Improvements

### GapFadeStrategy
- **Win Rate**: 30.0% (< 40%)
- **Analysis**: Fading gaps without trend confirmation often leads to losses in strong momentum markets ('Gap and Go').
- **Improvement**: Add a 'Reversal Candle' check (e.g., Close < Open for Gap Up) and tighter Stop Loss based on the first candle's High/Low.
