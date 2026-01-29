# Strategy Prioritization Report

This report prioritizes all strategies present in the repository using equal
weights across performance, risk readiness, operational readiness, and business
importance. Sources include strategy docs and available strategy inventories
under `openalgo/`, `openalgo_backup_20260128_164229/`, and `AITRAPP/`.

## Inventory (by location)

### OpenAlgo (current)
- `openalgo/strategies/scripts/mcx_ai_enhanced_strategy.py`
- `openalgo/strategies/scripts/mcx_advanced_strategy.py`
- `openalgo/strategies/scripts/mcx_elite_strategy.py`
- `openalgo/strategies/scripts/mcx_neural_strategy.py`
- `openalgo/strategies/scripts/mcx_quantum_strategy.py`
- `openalgo/strategies/scripts/mcx_advanced_momentum_strategy.py`
- `openalgo/strategies/scripts/mcx_commodity_momentum_strategy.py`
- `openalgo/strategies/scripts/mcx_clawdbot_strategy.py`
- `openalgo/strategies/scripts/mcx_global_arbitrage_strategy.py`
- `openalgo/strategies/scripts/crude_oil_clawdbot_strategy.py`
- `openalgo/strategies/scripts/crude_oil_enhanced_strategy.py`
- `openalgo/strategies/scripts/natural_gas_clawdbot_strategy.py`
- `openalgo/strategies/scripts/mcx_quantum_strategy.py`
- `openalgo/strategies/examples/simple_ema_strategy.py`

### OpenAlgo backup (archived but documented)
- `openalgo_backup_20260128_164229/strategies/scripts/ai_hybrid_reversion_breakout.py`
- `openalgo_backup_20260128_164229/strategies/scripts/advanced_ml_momentum_strategy.py`
- `openalgo_backup_20260128_164229/strategies/scripts/supertrend_vwap_strategy.py`
- `openalgo_backup_20260128_164229/strategies/scripts/orb_strategy.py`
- `openalgo_backup_20260128_164229/strategies/scripts/trend_pullback_strategy.py`
- `openalgo_backup_20260128_164229/strategies/scripts/sector_momentum_strategy.py`
- `openalgo_backup_20260128_164229/strategies/scripts/advanced_equity_strategy.py`
- `openalgo_backup_20260128_164229/strategies/scripts/multi_timeframe_momentum_strategy.py`
- `openalgo_backup_20260128_164229/strategies/scripts/delta_neutral_iron_condor_nifty.py`
- `openalgo_backup_20260128_164229/strategies/scripts/mcx_*` (same MCX set as current)

### AITRAPP (core)
- `AITRAPP/AITRAPP/packages/core/strategies/orb.py`
- `AITRAPP/AITRAPP/packages/core/strategies/orb_trend.py`
- `AITRAPP/AITRAPP/packages/core/strategies/trend_pullback.py`
- `AITRAPP/AITRAPP/packages/core/strategies/mean_reversion_bb.py`
- `AITRAPP/AITRAPP/packages/core/strategies/iron_condor.py`
- `AITRAPP/AITRAPP/packages/core/strategies/options_ranker.py`

## Scoring rubric (equal weights)

Each strategy is scored 1–5 for each category, then averaged.
- Performance (docs/backtests)
- Risk readiness (risk controls, limits, sizing)
- Operational readiness (configs, runners, monitoring, docs)
- Business importance (explicit recommendations in docs)

If a metric is missing, score conservatively and mark as a gap.

## Ranked priorities (top to bottom)

| Rank | Strategy | Performance | Risk | Ops | Business | Score | Action | Notes |
|------|----------|-------------|------|-----|----------|-------|--------|-------|
| 1 | AI Hybrid Reversion + Breakout | 5 | 5 | 3 | 5 | 4.5 | Deploy | Best overall in `ALL_STRATEGIES_COMPARISON.md`; verify current code location (archived file). |
| 2 | Advanced ML Momentum | 5 | 4 | 3 | 4 | 4.0 | Deploy | Strong docs and targets in `ADVANCED_ML_STRATEGY.md`. |
| 3 | MCX Commodity Momentum (enhanced) | 4 | 5 | 4 | 4 | 4.25 | Deploy | Live enhancements documented in `MCX_STRATEGY_ENHANCEMENTS_DEPLOYED.md`. |
| 4 | SuperTrend VWAP | 4 | 3 | 3 | 4 | 3.5 | Paper trade | Strong demo ranking but lower risk depth. |
| 5 | ORB | 3 | 2 | 3 | 3 | 2.75 | Paper trade | Specialized to opening volatility; lower adaptability. |
| 6 | Trend Pullback | 3 | 3 | 2 | 2 | 2.5 | Optimize | Mixed results in demo ranking. |
| 7 | MCX AI Enhanced | 3 | 3 | 3 | 2 | 2.75 | Paper trade | Needs documented performance metrics. |
| 8 | MCX Advanced Momentum | 3 | 3 | 3 | 2 | 2.75 | Paper trade | Similar to MCX set; needs metrics. |
| 9 | MCX Global Arbitrage | 3 | 3 | 2 | 2 | 2.5 | Optimize | Needs backtest report and operational guide. |
| 10 | MCX Elite / Neural / Quantum | 2 | 2 | 2 | 2 | 2.0 | Hold | No documented metrics; treat as experimental. |
| 11 | Clawdbot strategies (Crude/NatGas/MCX) | 2 | 2 | 2 | 2 | 2.0 | Hold | No ranking data; need validation. |
| 12 | Options: Delta Neutral Iron Condor / AITRAPP Iron Condor | 2 | 3 | 2 | 2 | 2.25 | Paper trade | Options risk model not documented. |
| 13 | Sector / Advanced Equity / Multi-timeframe Momentum | 2 | 2 | 2 | 2 | 2.0 | Hold | No performance metrics available. |
| 14 | AITRAPP ORB / Trend / Mean Reversion | 2 | 2 | 2 | 2 | 2.0 | Hold | Use as research baselines. |
| 15 | Simple EMA (example) | 1 | 1 | 1 | 1 | 1.0 | Hold | Example-only strategy. |

## Gaps blocking promotion

- Many strategies lack current backtest metrics in the main repo.
- Several high-performing strategies live in the backup folder; decide whether to port them into `openalgo/strategies/scripts/`.
- Options strategies need explicit risk controls and documented max loss scenarios.
- MCX variants (elite/neural/quantum) lack performance evidence.

## Next steps for top 3

1. AI Hybrid Reversion + Breakout
   - Move strategy into current `openalgo/strategies/scripts/` if it remains in backup.
   - Validate with current paper trading runner and log metrics.

2. Advanced ML Momentum
   - Run paper trading and export metrics for confirmation against targets.
   - Confirm deployment checklist and configuration values.

3. MCX Commodity Momentum (enhanced)
   - Keep as primary MCX live candidate with current risk controls.
   - Add standardized performance report output for weekly review.
