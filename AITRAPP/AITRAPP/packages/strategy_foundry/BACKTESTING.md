# Backtesting Protocol

## Intraday Assumptions
- **Execution**: Signal calculated on Bar Close (T), Executed at Open (T+1).
- **Session**: Market Open 09:15, Close 15:30 IST.
- **Forced Exit**: All positions are closed at 15:25 IST (Hard Close).
- **Data**: Yahoo Finance 5m/15m (approx 60 days history). Daily (10 years).

## Costs & Slippage
- **Slippage**: 5 bps per side.
- **Tax/Charges**: 3 bps per side.
- **Brokerage**: Fixed Rs 20 per order (ignored in % return calculation, relied on bps friction).
- **Spread Guard**: Additional penalty for choppy markets.

## Walk-Forward Evaluation
- **Method**: K-Fold Time-Series Split.
- **Folds**: 4 (Full Mode), 2 (Fast Mode).
- **Metric**: OOS Performance (Sharpe, Calmar, Return).
- **Stability**: Variance of Sharpe Ratio across folds.

## Rejection Criteria
Strategies are rejected if:
- **Trades**: < 60 (5m) or < 30 (15m).
- **Drawdown**: > 30%.
- **Profit Factor**: < 1.1.
- **Win Rate**: < 35%.
- **Sanity**: Daily (1D) Sharpe < -0.2 or MaxDD > 45%.
- **Late Day Dependence**: > 70% of profit comes from trades closing after 15:00.
- **Overtrading**: > 10 trades/day avg.

## Ranking
- **Blended Score**: `0.6 * Score_15m + 0.4 * Score_5m`.
- **Promotion**: Challenger must beat Champion Score by 10% OR Reduce MaxDD by 5% (with Sharpe parity).
