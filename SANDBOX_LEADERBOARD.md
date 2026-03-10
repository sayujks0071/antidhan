# SANDBOX LEADERBOARD (2026-02-24)

| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |
|------|----------|---------------|--------------|----------|--------------|
| 1 | AdvancedMLMomentum | Inf | 0.00 | 100.0% | 5 |
| 2 | SuperTrendVWAP | 1.73 | 313.00 | 70.0% | 10 |
| 3 | GapFadeStrategy | 0.52 | 805.00 | 30.0% | 10 |

## Analysis & Improvements

### GapFadeStrategy
- **Win Rate**: 30.0% (< 40%)
- **Analysis**: Fading gaps without trend confirmation often leads to losses in strong momentum markets ('Gap and Go').
- **Improvement**: Add a 'Reversal Candle' check (e.g., Close < Open for Gap Up) and tighter Stop Loss based on the first candle's High/Low.
- **Action**: Updated `openalgo/strategies/scripts/gap_fade_strategy.py` with ADX trend filter (< 25) and RSI confirmation (> 60 / < 40) to filter out strong trend days.
