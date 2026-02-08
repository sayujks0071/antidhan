# Cross-Strategy Correlation Analysis

## Strategies Analyzed
1. **SuperTrend VWAP Strategy** (`supertrend_vwap_strategy.py`)
   - **Type**: Trend Following (Intraday)
   - **Asset Class**: Equity / Index (e.g., NIFTY)
   - **Key Indicators**: VWAP, Volume Profile (POC), Sector Correlation.
   - **Timeframe**: Intraday (VWAP resets daily), Logic runs on fetched history (30 days used for context but indicators are intraday).

2. **AI Hybrid Reversion Breakout** (`ai_hybrid_reversion_breakout.py`)
   - **Type**: Hybrid (Mean Reversion & Breakout)
   - **Asset Class**: Equity (e.g., RELIANCE)
   - **Key Indicators**: RSI (30/60), Bollinger Bands (20, 2), VIX, Market Breadth.
   - **Timeframe**: 5-minute candles.

3. **MCX Commodity Momentum** (`mcx_commodity_momentum_strategy.py`)
   - **Type**: Momentum
   - **Asset Class**: Commodity (e.g., SILVER, GOLD)
   - **Key Indicators**: ADX (>25), RSI (45/55), Seasonality, USD/INR Volatility.
   - **Timeframe**: 15-minute candles.

## Logic Comparison

| Feature | SuperTrend VWAP | AI Hybrid | MCX Momentum |
| :--- | :--- | :--- | :--- |
| **Trigger** | Close > VWAP + Vol Spike | RSI < 30 (Rev) OR RSI > 60 (Break) | ADX > 25 + RSI > 55 (Buy) / < 45 (Sell) |
| **Confirmation** | Sector Correlation | Market Breadth + VIX | Seasonality + Global Alignment |
| **Exit** | Trailing Stop (ATR) or VWAP Cross | 1% Target/Stop or SMA20 Reversion | RSI/ADX Fade or Trend Reversal |
| **Overlap Potential** | High with NIFTY-linked assets | High with NIFTY-linked assets | Low (Commodities uncorrelated with Equities intraday) |

## Correlation Findings

1.  **Equity Correlation**: `SuperTrendVWAP` (NIFTY) and `AIHybrid` (RELIANCE) operate on correlated assets. However, their logic differs significantly:
    - `SuperTrendVWAP` waits for a *confirmed trend* (Price > VWAP) with volume support.
    - `AIHybrid` enters on *extremes* (RSI < 30) for mean reversion, or *strong momentum* (RSI > 60) for breakout.
    - **Scenario**: In a strong uptrend, `SuperTrendVWAP` will likely be Long. `AIHybrid` might be Long (Breakout) or Short (Mean Reversion if overextended). This divergence reduces correlation.
    - **Risk**: During a market crash, `SuperTrendVWAP` will likely be Short (Price < VWAP). `AIHybrid` might attempt to catch the falling knife (RSI < 30 Mean Reversion). This is a *negative correlation* which is good for hedging, but risky if the crash continues.

2.  **Commodity Decoupling**: `MCX Momentum` trades commodities which generally have low correlation with Indian Equities intraday. This provides excellent diversification.

## Conclusion

The strategies show **low to moderate correlation** due to:
1.  **Asset Class Diversification** (Equity vs Commodity).
2.  **Logic Diversification** (Trend vs Mean Reversion).

**Recommendation**:
- **Do NOT Merge**. The strategies serve different purposes and operate on different regimes.
- **Maintain Separate Execution**. Merging would complicate the logic without significant benefit.
- **Risk Management**: Ensure `AIHybrid`'s mean reversion logic has strict stops (which it does: 1% stop) to avoid large losses during strong trends where `SuperTrendVWAP` might be profitable.
