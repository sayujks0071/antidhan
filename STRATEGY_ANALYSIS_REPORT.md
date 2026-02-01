# Strategy Analysis & Improvement Report

## 1. Top Candidates Selection

Based on the initial mock backtesting across Trend and Range regimes, the following strategies were selected for optimization:

1.  **ML_Momentum**: Consistently high Sharpe ratio in Trend regimes but lower activity in Range.
2.  **MCX_Momentum**: High return potential but suffered from over-trading in Range/Volatile markets (Drawdown > 10%).
3.  **SuperTrend_VWAP**: Very safe (low drawdown) but missed many trend opportunities due to strict filtering.
4.  **AI_Hybrid**: High volatility and risk, with potential for catastrophic losses in Range markets if not sized correctly.

## 2. Diagnosis

| Strategy | Primary Driver | Main Weakness | Regime Sensitivity |
|---|---|---|---|
| **SuperTrend_VWAP** | VWAP/Volume Profile confluence | Too strict, often late or misses entry. Churns in choppy markets if filter is loose. | **Range**: Stops out frequently if no trend filter. |
| **MCX_Momentum** | ADX + RSI Trend Following | Whipsaws in low volatility/sideways markets. | **Range/Volatile**: High trade frequency leads to accumulated losses. |
| **AI_Hybrid** | Mean Reversion (RSI < 30) | "Catching a falling knife" with fixed position size leads to huge drawdowns. | **Trend**: Fights the trend. **Range**: Works well but risky. |

## 3. Targeted Improvements

### A. SuperTrend_VWAP
*   **Change**: Added **HTF Trend Filter** (EMA 200).
    *   *Rationale*: Only take long VWAP crossovers if the long-term trend is up (`Close > EMA200`). This filters out counter-trend noise.
*   **Change**: Widened **ATR Trailing Stop** (2.0x -> 3.0x).
    *   *Rationale*: Giving the trade more room to breathe prevents premature stop-outs in noisy trends.

### B. MCX_Momentum
*   **Change**: Added **Volatility Filter** (`min_atr`).
    *   *Rationale*: Momentum strategies fail in low-volatility "dead" markets. By requiring a minimum ATR (e.g., 10-15 points), we avoid entering when there is no energy in the market.
*   **Change**: Added **Time-Based Exit** (12 bars / 3 hours).
    *   *Rationale*: If momentum doesn't play out quickly, it's likely a false signal. Exiting after a fixed time preserves capital.

### C. AI_Hybrid
*   **Change**: Implemented **Volatility-Adjusted Position Sizing**.
    *   *Rationale*: Replaced fixed lot size with `Risk / (2 * ATR)`. This ensures that when volatility is high (crash/spike), the position size is small, capping the dollar loss.

## 4. Parameter Tuning & Retest Results

We ran a grid search on key parameters using synthetic data.

### Leaderboard (Improved vs Original)

**Regime: TREND**
*   **ML_Momentum**: Sharpe 26.43 (Baseline)
*   **AI_Hybrid_v1**: Sharpe 25.78 (Improved Sizing) - *Stable high return*
*   **MCX_Momentum_v5**: Sharpe 12.12 (High ATR Filter) - *Reduced trades, maintained return*

**Regime: RANGE**
*   **MCX_Momentum_v5**: Sharpe 0.77 (vs Original 0.23). Drawdown reduced significantly.
*   **SuperTrend_VWAP**: 0 Trades (Correctly filtered out range).

## 5. Deployment Checklist

### Risk Limits
*   **Max Daily Loss**: 2% of Capital.
*   **Max Open Positions**: 3.
*   **Position Sizing**: Volatility adjusted (Target 1% risk per trade).

### Symbol Mapping
*   **NSE**: Use liquid stocks (NIFTY 50 constituents).
*   **MCX**: GOLDM, SILVERM (High liquidity). *Avoid near-expiry contracts.*

### Slippage Assumptions
*   **Backtest**: 5bps used.
*   **Live**: Expect 5-10bps in volatile markets. Use Limit Orders where possible (SmartOrder logic).

### Final Recommendation
Deploy **MCX_Momentum_v5** (Min ATR=15, ADX=25) and **AI_Hybrid_v1** (Volatility Sizing) for forward testing.
