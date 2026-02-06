# DAILY STATUS REPORT

## Sandbox Performance Summary (Past Week)

**Net PnL:** ₹577,330.95
**Master Contracts:** All Contracts Synced

### Strategy Ranking

| Rank | Strategy | Profit Factor | Net PnL (₹) | Win Rate | Status |
|------|----------|---------------|-------------|----------|--------|
| 1 | **SuperTrendVWAP** | **12.11** | 209,538.52 | 75.0% | **ALPHA** (Promoted to V2) |
| 2 | TrendPullback | 4.79 | 12,728.22 | 54.2% | Active |
| 3 | ORB | 4.77 | 355,064.21 | 73.3% | Active (High PnL) |
| - | GapFadeStrategy | N/A | 0.00 | N/A | **RETIRED** (Laggard) |

---

## Infrastructure Updates

*   **Refactoring:** Centralized `calculate_ema` and `calculate_sma` in `trading_utils.py` to ensure DRY principles.
*   **Innovation:** Deployed `SuperTrendVWAPStrategyV2` with **Multi-Timeframe Confirmation** (Daily EMA 200 Trend Filter) to address drawdowns.
*   **Deprecation:** Moved `GapFadeStrategy` to `strategies/retired/` due to inactivity/performance concerns.

## Recommendations for Next Week

1.  **Target Symbols:** Focus on high-beta sectors (BANKNIFTY) where `SuperTrendVWAP` excels.
2.  **Monitor V2:** detailed logs for `SuperTrendVWAPStrategyV2` to verify the effectiveness of the Daily Trend Filter.
3.  **Risk Management:** `ORB` has high PnL but lower Profit Factor; ensure position sizing is monitored during volatility spikes.
