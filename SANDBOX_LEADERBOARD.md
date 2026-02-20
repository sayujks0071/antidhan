# SANDBOX LEADERBOARD (2026-02-20)

| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |
|------|----------|---------------|--------------|----------|--------------|
| 1 | SuperTrendVWAP | 1.20 | 259.00 | 60.0% | 10 |
| 2 | AdvancedMLMomentum | 1.20 | 229.00 | 60.0% | 5 |
| 3 | GapFadeStrategy | 0.54 | 735.00 | 30.0% | 10 |

## Analysis & Improvements

### GapFadeStrategy
- **Win Rate**: 30.0% (< 40%)
- **Analysis**: Fading gaps without trend confirmation often leads to losses in strong momentum markets ('Gap and Go').
- **Improvement**: Add a 'Reversal Candle' check (e.g., Close < Open for Gap Up) and tighter Stop Loss based on the first candle's High/Low.
- **Action**: Updated `openalgo/strategies/scripts/gap_fade_strategy.py` with ADX trend filter (< 25) and RSI confirmation (> 60 / < 40) to filter out strong trend days.
