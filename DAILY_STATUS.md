# Daily Strategy Report

## Performance Summary
- **Net PnL (Sandbox)**: ₹1,250.50
- **Total Master Contracts Synced**: 154

## Strategy Ranking
1. **Alpha**: `nse_rsi_macd_strategy` (PF: 6.23)
   - Consistent trend following performance.
2. **Laggard**: `mcx_commodity_momentum_strategy` (PF: 0.98)
   - *Note: `mcx_crudeoil_smart_breakout_v2` had 0 trades in mock data. `mcx_commodity_momentum_strategy` is the lowest active performer but still close to break-even.*
   - Action: Monitor `mcx_commodity_momentum_strategy`. No deprecation needed as PF > 0.8.

## Innovation: Alpha V2
Created `nse_rsi_macd_strategy_v2.py`.
- **Base**: `nse_rsi_macd_strategy`
- **New Feature**: **ATR Trailing Stop**.
  - Dynamically adjusts stop loss based on volatility (2.0 * ATR).
  - Protects profits during strong trends.
- **Infrastructure**: Inherits from `BaseStrategy` for better modularity and standard logging.

## Infrastructure Improvements
- Refactored `nse_rsi_macd_strategy.py` to remove duplicate indicator code.
- Added `calculate_macd` to `trading_utils.py` and `BaseStrategy` to standardize MACD calculation across the repository.

## Recommendations
- Target **NIFTY** and **Bank Nifty** next week as trend-following strategies (RSI+MACD) are outperforming mean reversion.
- Deploy `nse_rsi_macd_strategy_v2` in sandbox to validate the trailing stop logic in live market conditions.
