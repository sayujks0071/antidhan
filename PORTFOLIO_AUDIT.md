# Portfolio Audit & Stress Test Report
**Date:** 2026-02-15

## 1. Cross-Strategy Correlation
| Strategy A | Strategy B | Correlation | Action |
|---|---|---|---|
| mcx_crudeoil_smart_breakout | mcx_naturalgas_momentum_strategy | 0.82 | Keep **mcx_crudeoil_smart_breakout** (Calmar: 0.54), Deprecate mcx_naturalgas_momentum_strategy |
| nse_rsi_macd_strategy | nse_rsi_macd_strategy_v2 | 1.00 | Keep **nse_rsi_macd_strategy_v2** (Calmar: 1.68), Deprecate nse_rsi_macd_strategy |
| mcx_crudeoil_trend_strategy | mcx_silver_momentum | 1.00 | Keep **mcx_silver_momentum** (Calmar: 0.31), Deprecate mcx_crudeoil_trend_strategy |
| nse_bollinger_rsi_strategy | nse_rsi_bol_trend | 1.00 | Keep **nse_rsi_bol_trend** (Calmar: 0.20), Deprecate nse_bollinger_rsi_strategy |
| mcx_silver_trend_strategy | mcx_naturalgas_momentum_strategy | 0.85 | Keep **mcx_naturalgas_momentum_strategy** (Calmar: 0.19), Deprecate mcx_silver_trend_strategy |
| mcx_aluminium_trend_strategy | mcx_gold_momentum_strategy | 0.81 | Keep **mcx_aluminium_trend_strategy** (Calmar: 0.46), Deprecate mcx_gold_momentum_strategy |
| advanced_ml_momentum_strategy | mcx_gold_momentum_strategy | 0.76 | Keep **mcx_gold_momentum_strategy** (Calmar: 0.35), Deprecate advanced_ml_momentum_strategy |

## 2. Equity Curve Stress Test
- **Worst Day:** 2026-02-01
- **Max Daily Loss:** ₹-3,021.70
- **Total Portfolio Return:** ₹3,909.24

### Root Cause Analysis
The worst day occurred during the simulated 'Market Crash' phase (Day 15).
Strategies relying on Mean Reversion without volatility filters likely suffered the most.

## 3. Strategy Performance Ranking
| Rank | Strategy | Profit Factor | Calmar Ratio | Win Rate |
|---|---|---|---|---|
| 1 | nse_rsi_macd_strategy | 3.51 | 1.68 | 71.4% |
| 2 | nse_rsi_macd_strategy_v2 | 3.51 | 1.68 | 71.4% |
| 3 | nse_ma_crossover_strategy | 2.09 | 0.74 | 71.4% |
| 4 | mcx_crudeoil_smart_breakout | 1.83 | 0.54 | 80.0% |
| 5 | mcx_aluminium_trend_strategy | 1.43 | 0.46 | 66.7% |
| 6 | mcx_gold_momentum_strategy | 1.35 | 0.35 | 66.7% |
| 7 | mcx_crudeoil_trend_strategy | 1.33 | 0.31 | 54.5% |
| 8 | mcx_silver_momentum | 1.33 | 0.31 | 54.5% |
| 9 | nse_bollinger_rsi_strategy | 1.22 | 0.20 | 58.3% |
| 10 | nse_rsi_bol_trend | 1.22 | 0.20 | 58.3% |
| 11 | mcx_naturalgas_momentum_strategy | 1.32 | 0.19 | 50.0% |
| 12 | mcx_silver_trend_strategy | 1.22 | 0.19 | 50.0% |
| 13 | advanced_ml_momentum_strategy | 1.12 | 0.12 | 50.0% |
| 14 | ai_hybrid_reversion_breakout | 0.00 | 0.00 | 0.0% |
| 15 | supertrend_vwap_strategy | 0.00 | 0.00 | 0.0% |
| 16 | mcx_crudeoil_smart_breakout_v2 | 0.00 | -0.76 | 0.0% |
| 17 | mcx_commodity_momentum_strategy | 0.55 | -0.76 | 39.3% |