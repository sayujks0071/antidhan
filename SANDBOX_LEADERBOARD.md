# SANDBOX LEADERBOARD (2026-03-05)

| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |
|------|----------|---------------|--------------|----------|--------------|
| 1 | AdvancedMLMomentum | Inf | 0.00 | 100.0% | 5 |
| 2 | SuperTrendVWAP | 0.39 | 547.00 | 30.0% | 10 |
| 3 | GapFadeStrategy | 0.32 | 819.00 | 30.0% | 10 |

## Analysis & Improvements

### GapFadeStrategy
- **Win Rate**: 30.0% (< 40%)
- **Analysis**: Fading gaps without trend confirmation often leads to losses in strong momentum markets ('Gap and Go').
- **Improvement**: Add a 'Reversal Candle' check (e.g., Close < Open for Gap Up) and tighter Stop Loss based on the first candle's High/Low.

### SuperTrendVWAP
- **Win Rate**: 30.0% (< 40%)
- **Suggestion**: Analyze entry conditions. Check log for rejections or stop loss tightness.

## All Trades Executed Today

| Strategy | Entry Time | Entry Price | Exit Time | Exit Price | PnL | Status |
|----------|------------|-------------|-----------|------------|-----|--------|
| GapFadeStrategy | 2026-03-05 09:25:00 | 24499.00 | 2026-03-05 09:30:00 | 24590.00 | 91.00 | CLOSED |
| SuperTrendVWAP | 2026-03-05 09:33:00 | 24207.00 | 2026-03-05 09:51:00 | 24049.00 | -158.00 | CLOSED |
| AdvancedMLMomentum | 2026-03-05 09:38:00 | 24281.00 | 2026-03-05 10:19:00 | 24460.00 | 179.00 | CLOSED |
| SuperTrendVWAP | 2026-03-05 10:15:00 | 24349.00 | 2026-03-05 10:27:00 | 24458.00 | 109.00 | CLOSED |
| GapFadeStrategy | 2026-03-05 10:25:00 | 24038.00 | 2026-03-05 10:43:00 | 24127.00 | 89.00 | CLOSED |
| AdvancedMLMomentum | 2026-03-05 10:27:00 | 24276.00 | 2026-03-05 11:23:00 | 24458.00 | 182.00 | CLOSED |
| GapFadeStrategy | 2026-03-05 11:21:00 | 24097.00 | 2026-03-05 12:16:00 | 24177.00 | 80.00 | CLOSED |
| SuperTrendVWAP | 2026-03-05 11:35:00 | 24476.00 | 2026-03-05 12:31:00 | 24561.00 | 85.00 | CLOSED |
| AdvancedMLMomentum | 2026-03-05 11:44:00 | 24334.00 | 2026-03-05 12:10:00 | 24436.00 | 102.00 | CLOSED |
| SuperTrendVWAP | 2026-03-05 12:19:00 | 24070.00 | 2026-03-05 13:12:00 | 23972.00 | -98.00 | CLOSED |
| GapFadeStrategy | 2026-03-05 12:32:00 | 24255.00 | 2026-03-05 13:10:00 | 24151.00 | -104.00 | CLOSED |
| AdvancedMLMomentum | 2026-03-05 12:43:00 | 24478.00 | 2026-03-05 13:03:00 | 24562.00 | 84.00 | CLOSED |
| AdvancedMLMomentum | 2026-03-05 13:17:00 | 24333.00 | 2026-03-05 13:36:00 | 24404.00 | 71.00 | CLOSED |
| GapFadeStrategy | 2026-03-05 13:31:00 | 24220.00 | 2026-03-05 14:02:00 | 24121.00 | -99.00 | CLOSED |
| SuperTrendVWAP | 2026-03-05 13:36:00 | 24472.00 | 2026-03-05 14:11:00 | 24406.00 | -66.00 | CLOSED |
| SuperTrendVWAP | 2026-03-05 14:17:00 | 24488.00 | 2026-03-05 14:33:00 | 24614.00 | 126.00 | CLOSED |
| GapFadeStrategy | 2026-03-05 14:32:00 | 24242.00 | 2026-03-05 15:23:00 | 24166.00 | -76.00 | CLOSED |
| GapFadeStrategy | 2026-03-05 15:23:00 | 24180.00 | 2026-03-05 16:14:00 | 24052.00 | -128.00 | CLOSED |
| SuperTrendVWAP | 2026-03-05 15:37:00 | 24045.00 | 2026-03-05 16:16:00 | 23945.00 | -100.00 | CLOSED |
| SuperTrendVWAP | 2026-03-05 16:41:00 | 24180.00 | 2026-03-05 17:10:00 | 24023.00 | -157.00 | CLOSED |
| GapFadeStrategy | 2026-03-05 16:42:00 | 24141.00 | 2026-03-05 17:25:00 | 23950.00 | -191.00 | CLOSED |
| SuperTrendVWAP | 2026-03-05 17:42:00 | 24094.00 | 2026-03-05 18:39:00 | 23983.00 | -111.00 | CLOSED |
| GapFadeStrategy | 2026-03-05 17:45:00 | 24017.00 | 2026-03-05 18:25:00 | 23958.00 | -59.00 | CLOSED |
| GapFadeStrategy | 2026-03-05 18:25:00 | 24158.00 | 2026-03-05 18:53:00 | 23996.00 | -162.00 | CLOSED |
| SuperTrendVWAP | 2026-03-05 18:35:00 | 24343.00 | 2026-03-05 19:27:00 | 24202.00 | -141.00 | CLOSED |
