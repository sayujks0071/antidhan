# DAILY STATUS REPORT

## Performance Summary (Sandbox)
*   **Net PnL**: Mixed.
    *   **Alpha (AdvancedMLMomentum)**: Profit Factor **1.66**. Max Drawdown: -241.00.
    *   **Laggard (GapFadeStrategy)**: Profit Factor **0.35**. Max Drawdown: -895.00.
    *   **SuperTrendVWAP**: Profit Factor **0.91**.

## Infrastructure Health
*   **Master Contracts**: N/A (Database `db/openalgo.db` not found or inaccessible).
*   **Refactoring**:
    *   `trading_utils.py` and `BaseStrategy` updated with `calculate_donchian_channel` and standard indicators to enforce DRY.
    *   6 Strategies refactored to use shared utility functions.

## Strategy Updates
*   **New Strategy**: `AdvancedMLMomentumV2` (Alpha V2)
    *   **Features**: Added Volatility Filter (ATR Expansion) and Trailing Stop (2.0 * ATR) to address drawdown.
*   **Deprecation**: `GapFadeStrategy` (Laggard) was identified for removal/archiving (file currently missing from active scripts).

## Recommendations for Next Week
*   **Target Symbols**: NIFTY 50, BANKNIFTY (High Liquidity for Momentum).
*   **Action**: Deploy `AdvancedMLMomentumV2`. The Volatility Filter should reduce false positives in choppy markets, and the Trailing Stop will protect gains better than the previous fixed stop.
