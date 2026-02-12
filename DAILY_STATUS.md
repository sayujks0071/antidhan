# DAILY STATUS REPORT - 2026-02-15

## 📊 Performance Summary (Sandbox)
- **Net PnL**: -1100.00
- **Total Master Contracts**: Not found locally (Synced on startup)

## 🏆 Strategy Rankings (Past Week)
| Rank | Strategy | Profit Factor | Status | Action |
|------|----------|---------------|--------|--------|
| **1 (Alpha)** | `AdvancedMLMomentum` | 9.08 | Active | **Upgraded to V2** (Added Volatility Filter & Trailing Stop) |
| 2 | `SuperTrendVWAP` | 3.57 | Active | Monitored |
| **3 (Laggard)** | `GapFadeStrategy` | 0.37 | Retired | **Confirmed Retired** |

## 🚀 Innovation: Advanced ML Momentum V2
The Alpha strategy has been upgraded to `AdvancedMLMomentumStrategyV2`.
- **New Feature 1: Volatility Filter**: Checks VIX. If VIX > 25, position size is reduced by 50% to protect capital during chop.
- **New Feature 2: Trailing Stop**: Implemented a dynamic trailing stop based on the highest price since entry to lock in profits.
- **Refactoring**: specific logic moved to `BaseStrategy` to keep code DRY.

## 📉 Deprecation
- `GapFadeStrategy` remains in `strategies/retired/` due to poor performance (PF 0.37).

## 💡 Recommendations for Next Week
- **Switch to V2**: Deploy `AdvancedMLMomentumStrategyV2` for NIFTY/BankNIFTY trading. The added volatility protection is crucial for the current market environment.
- **Monitor SuperTrend**: Keep an eye on `SuperTrendVWAP`. It is profitable but had a significant drawdown.
