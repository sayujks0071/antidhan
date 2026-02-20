# SANDBOX LEADERBOARD (2026-02-17)

| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |
|------|----------|---------------|--------------|----------|--------------|
| 1 | NSE_RSI_MACD_Strategy | 0.00 | 65.00 | 0.0% | 3 |

## Analysis & Improvements

### NSE_RSI_MACD_Strategy
- **Win Rate**: 0.0% (< 40%)
- **Analysis**: Basic MACD crossover in choppy markets generates false signals. RSI alone is insufficient filter.
- **Improvement**: Add ADX Filter (ADX > 25) to ensure trend strength and inherit from BaseStrategy for robust execution.
