# SANDBOX LEADERBOARD (2026-02-25)

| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |
|------|----------|---------------|--------------|----------|--------------|
| 1 | AdvancedMLMomentum | 11.12 | 50.00 | 80.0% | 5 |
| 2 | SuperTrendVWAP | 1.21 | 312.00 | 40.0% | 10 |
| 3 | GapFadeStrategy | 0.48 | 750.00 | 30.0% | 10 |

## Analysis & Improvements

### GapFadeStrategy
- **Win Rate**: 30.0% (< 40%)
- **Analysis**: Fading gaps without trend confirmation often leads to losses in strong momentum markets ('Gap and Go').
- **Improvement**: Add a 'Reversal Candle' check (e.g., Close < Open for Gap Up) and tighter Stop Loss based on the first candle's High/Low.
- **Action**: Strategy source code (`openalgo/strategies/scripts/gap_fade_strategy.py`) is missing from the repository. Marked for retirement/investigation.
