# Daily Status Report (2026-02-08)

## 1. Net PnL in Sandbox
**Total Net PnL:** -157.00 (Estimated from last 7 days mock data)

### Breakdown by Strategy (Top/Bottom)
| Rank | Strategy | Net PnL | Profit Factor | Status |
|------|----------|---------|---------------|--------|
| 1 | AdvancedMLMomentum | +1957.00 | 4.97 | **Alpha** (Active) |
| 2 | OptionsRanker | +1099.00 | 2.22 | Active |
| 3 | MCXSilverMomentum | +426.00 | 1.54 | Active |
| ... | ... | ... | ... | ... |
| 9 | GapFadeStrategy | -2192.00 | 0.22 | **Deprecated** (Moved to Retired) |

## 2. Infrastructure Updates
- **Refactoring:** Moved `calculate_sma`, `calculate_ema`, and `calculate_relative_strength` to `trading_utils.py` to support DRY principles.
- **Fixes:** `BaseStrategy` now properly wraps these indicators.
- **Innovation:** Introduced `AdvancedMLMomentumV2` with a **Volatility Filter (ATR Threshold)** to reduce chop in flat markets.

## 3. Master Contracts
- Master contracts synced successfully for NSE and MCX segments.

## 4. Recommendations for Next Week
- **Target Symbols:** NIFTY, BANKNIFTY (via AdvancedMLMomentum).
- **Strategy Focus:** Deploy `AdvancedMLMomentumV2` to production/sandbox to test the new Volatility Filter.
- **Action:** Monitor `OptionsRanker` as a potential secondary Alpha.
