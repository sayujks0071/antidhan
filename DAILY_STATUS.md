# DAILY STATUS REPORT

## Strategy Performance (Mock Sandbox)

**Period:** Past Week (Feb 7 - Feb 14, 2026)

| Rank | Strategy | Profit Factor | Net Return | Drawdown | Trades |
|------|----------|---------------|------------|----------|--------|
| **1 (Alpha)** | `nse_rsi_macd_strategy` | 6.23 | ₹10.54 | 0.00% | 7 |
| 2 | `nse_rsi_macd_strategy_v2` | 6.23 | ₹10.54 | 0.00% | 7 |
| 3 | `mcx_crudeoil_smart_breakout` | 6.17 | ₹6.17 | 0.00% | 4 |
| 4 | `nse_bollinger_rsi_strategy` | 5.21 | ₹8.47 | 0.00% | 6 |
| 6 | `nse_ma_crossover_strategy` | 4.36 | ₹6.93 | 0.00% | 6 |
| 11 | `nse_ma_crossover_strategy_v2` | 2.10 | ₹3.92 | 0.00% | 7 |
| 17 (Laggard) | `mcx_crudeoil_smart_breakout_v2` | 0.00 | ₹0.00 | 0.00% | 0 |

*Note: Returns are minimal/zero due to mock data generation properties. Rankings are based on Profit Factor.*

## Innovation: Alpha V2
We targeted `nse_ma_crossover_strategy` (Rank 6) for the "Version 2" innovation because the absolute Alpha (`nse_rsi_macd_strategy`) **already has a Version 2 deployed** (`nse_rsi_macd_strategy_v2` at Rank 2).

We created `nse_ma_crossover_strategy_v2.py` with:
- **Base Logic:** SMA 20/50 Crossover.
- **New Feature 1 (Volatility Filter):** Entries are now filtered by `ATR(14) > SMA(ATR, 10)` to ensure sufficient market movement.
- **New Feature 2 (Trailing Stop):** Implemented an ATR-based Trailing Stop (2.0 * ATR) to protect profits during trends.

## Deprecation
- **Laggard:** `mcx_crudeoil_smart_breakout_v2`
- **Action:** None (0 trades executed, inconclusive data).

## Infrastructure
- **Critical Fix:** Added `calculate_macd` to `strategies/utils/trading_utils.py` to fix import errors across multiple strategies.
- Refactored `mcx_crudeoil_smart_breakout.py` and `nse_bollinger_rsi_strategy.py` to use `BaseStrategy.calculate_bollinger_bands` instead of duplicate imports.

## Recommendations for Next Week
Based on the top performance of Momentum/Trend strategies:
1.  **Target Symbols:** Stocks showing clear trends with expanding volatility.
2.  **Strategy:** Focus on `nse_rsi_macd_strategy` and `nse_ma_crossover_strategy`.
3.  **Watchlist:** Look for symbols where SMA 20 is approaching SMA 50 from below (potential Golden Cross) AND ATR is rising.

## System Health
- **Total Master Contracts Synced:** N/A (Mock Environment)
- **Code Health:** Significantly improved by fixing missing utility functions and reducing code duplication.
