# SANDBOX LEADERBOARD (2026-03-02)

| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |
|------|----------|---------------|--------------|----------|--------------|
| 1 | AdvancedMLMomentum | Inf | 0.00 | 100.0% | 5 |
| 2 | SuperTrendVWAP | 2.31 | 308.00 | 70.0% | 10 |
| 3 | GapFadeStrategy | 0.33 | 1007.00 | 30.0% | 10 |

## Trade Log Summary

| Strategy | Direction | Entry Time | Entry Price | Exit Time | Exit Price | PnL |
|----------|-----------|------------|-------------|-----------|------------|-----|
| GapFadeStrategy | LONG | 2026-03-02 09:17:00 | 24420.00 | 2026-03-02 10:17:00 | 24531.00 | 111.00 |
| SuperTrendVWAP | LONG | 2026-03-02 09:19:00 | 24283.00 | 2026-03-02 10:13:00 | 24456.00 | 173.00 |
| AdvancedMLMomentum | LONG | 2026-03-02 09:20:00 | 24041.00 | 2026-03-02 09:29:00 | 24241.00 | 200.00 |
| AdvancedMLMomentum | LONG | 2026-03-02 10:32:00 | 24471.00 | 2026-03-02 11:04:00 | 24584.00 | 113.00 |
| GapFadeStrategy | LONG | 2026-03-02 10:34:00 | 24223.00 | 2026-03-02 11:08:00 | 24274.00 | 51.00 |
| SuperTrendVWAP | LONG | 2026-03-02 10:45:00 | 24150.00 | 2026-03-02 10:52:00 | 24304.00 | 154.00 |
| GapFadeStrategy | LONG | 2026-03-02 11:17:00 | 24470.00 | 2026-03-02 11:32:00 | 24645.00 | 175.00 |
| AdvancedMLMomentum | LONG | 2026-03-02 11:38:00 | 24406.00 | 2026-03-02 11:49:00 | 24484.00 | 78.00 |
| SuperTrendVWAP | LONG | 2026-03-02 11:38:00 | 24319.00 | 2026-03-02 12:11:00 | 24123.00 | -196.00 |
| AdvancedMLMomentum | LONG | 2026-03-02 12:28:00 | 24050.00 | 2026-03-02 12:56:00 | 24204.00 | 154.00 |
| GapFadeStrategy | LONG | 2026-03-02 12:31:00 | 24027.00 | 2026-03-02 12:45:00 | 23884.00 | -143.00 |
| SuperTrendVWAP | LONG | 2026-03-02 12:39:00 | 24365.00 | 2026-03-02 13:37:00 | 24253.00 | -112.00 |
| AdvancedMLMomentum | LONG | 2026-03-02 13:25:00 | 24357.00 | 2026-03-02 14:00:00 | 24547.00 | 190.00 |
| SuperTrendVWAP | LONG | 2026-03-02 13:28:00 | 24472.00 | 2026-03-02 13:39:00 | 24623.00 | 151.00 |
| GapFadeStrategy | LONG | 2026-03-02 13:36:00 | 24408.00 | 2026-03-02 14:15:00 | 24221.00 | -187.00 |
| GapFadeStrategy | LONG | 2026-03-02 14:29:00 | 24010.00 | 2026-03-02 15:18:00 | 23928.00 | -82.00 |
| SuperTrendVWAP | LONG | 2026-03-02 14:33:00 | 24262.00 | 2026-03-02 14:55:00 | 24318.00 | 56.00 |
| GapFadeStrategy | LONG | 2026-03-02 15:44:00 | 24210.00 | 2026-03-02 15:58:00 | 24052.00 | -158.00 |
| SuperTrendVWAP | LONG | 2026-03-02 15:45:00 | 24053.00 | 2026-03-02 16:13:00 | 24218.00 | 165.00 |
| SuperTrendVWAP | LONG | 2026-03-02 16:23:00 | 24172.00 | 2026-03-02 17:00:00 | 24268.00 | 96.00 |
| GapFadeStrategy | LONG | 2026-03-02 16:44:00 | 24016.00 | 2026-03-02 17:15:00 | 23824.00 | -192.00 |
| GapFadeStrategy | LONG | 2026-03-02 17:32:00 | 24497.00 | 2026-03-02 18:23:00 | 24411.00 | -86.00 |
| SuperTrendVWAP | LONG | 2026-03-02 17:34:00 | 24171.00 | 2026-03-02 18:10:00 | 24086.00 | -85.00 |
| GapFadeStrategy | LONG | 2026-03-02 18:27:00 | 24373.00 | 2026-03-02 18:58:00 | 24214.00 | -159.00 |
| SuperTrendVWAP | LONG | 2026-03-02 18:32:00 | 24040.00 | 2026-03-02 18:51:00 | 24153.00 | 113.00 |

## Analysis & Improvements

### GapFadeStrategy
- **Win Rate**: 30.0% (< 40%)
- **Analysis**: Fading gaps without trend confirmation often leads to losses in strong momentum markets ('Gap and Go').
- **Improvement**: Add a 'Reversal Candle' check (e.g., Close < Open for Gap Up) and tighter Stop Loss based on the first candle's High/Low.
- **Action**: Updated `openalgo/strategies/scripts/gap_fade_strategy.py` with ADX trend filter (< 25) and RSI confirmation (> 60 / < 40) to filter out strong trend days.
