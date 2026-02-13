# SANDBOX LEADERBOARD (2026-02-13)

| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |
|------|----------|---------------|--------------|----------|--------------|
| 1 | AdvancedMLMomentum | inf | 0.0 | 100.0% | 5 |
| 2 | SuperTrendVWAP | 2.38 | 168.0 | 70.0% | 10 |
| 3 | GapFadeStrategy | 0.5 | 818.0 | 30.0% | 10 |

## Analysis & Improvements

### GapFadeStrategy
- **Win Rate**: 30.0% (< 40%)
- **Analysis**: Fading gaps without trend confirmation often leads to losses in strong momentum markets ('Gap and Go').
- **Improvement**: Add a 'Reversal Candle' check (e.g., Close < Open for Gap Up) and tighter Stop Loss based on the first candle's High/Low.
