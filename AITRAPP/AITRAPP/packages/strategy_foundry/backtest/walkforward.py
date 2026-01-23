import pandas as pd
import numpy as np
from typing import List, Dict
from packages.strategy_foundry.backtest.engine import BacktestEngine
from packages.strategy_foundry.backtest.metrics import MetricCalculator
from packages.strategy_foundry.factory.grammar import StrategyConfig
from packages.strategy_foundry.adapters.core_costs import CostModel

class WalkForwardEvaluator:
    def __init__(self, df: pd.DataFrame, folds: int = 4, cost_model: CostModel = None):
        self.df = df
        self.folds = folds
        self.cost_model = cost_model
        if self.cost_model is None:
            # Default fallback if not provided
            self.cost_model = CostModel(slippage_bps=5.0, brokerage_per_order=20.0, tax_bps=3.0, spread_guard_bps=2.0)
        self.engine = BacktestEngine(self.cost_model)

    def evaluate(self, config: StrategyConfig, instrument_type: str = 'FUTURE') -> List[Dict]:
        """
        Splits data into K folds and evaluates strategy on each.
        Returns list of metrics dictionaries (one per fold).
        """
        n = len(self.df)
        fold_size = n // self.folds

        results = []

        # Calculate time span of whole DF for annualized metrics?
        # Or calculate per fold.

        for i in range(self.folds):
            start_idx = i * fold_size
            end_idx = (i + 1) * fold_size if i < self.folds - 1 else n

            fold_df = self.df.iloc[start_idx:end_idx].copy()

            # Run Engine
            trades = self.engine.run(fold_df, config)

            # Calculate Metrics
            # Time span in years
            start_date = fold_df['datetime'].iloc[0]
            end_date = fold_df['datetime'].iloc[-1]
            days = (end_date - start_date).days
            years = days / 365.25
            if years < 0.01: years = 0.01 # Avoid div by zero

            metrics = MetricCalculator.compute(trades, years)
            metrics['fold'] = i + 1
            metrics['start_date'] = start_date
            metrics['end_date'] = end_date

            # Sanity Checks (Intraday specific)
            # Late-day dependence
            # Overtrade penalty
            self._apply_sanity_penalties(metrics, trades, fold_df)

            results.append(metrics)

        return results

    def _apply_sanity_penalties(self, metrics: Dict, trades: pd.DataFrame, df: pd.DataFrame):
        # 1. Overtrade Penalty
        # Count trades per day
        if trades.empty:
            return

        if 'datetime' in df.columns:
            # Match trades to dates?
            # Trades has indices entry_idx.
            # We can map entry_idx to date.
            entry_indices = trades['entry_idx'].values
            trade_dates = df['datetime'].iloc[entry_indices].dt.date
            trades_per_day = pd.Series(trade_dates).value_counts()
            avg_trades_per_day = trades_per_day.mean()

            metrics['avg_trades_per_day'] = avg_trades_per_day

            # If > 10 trades per day?
            if avg_trades_per_day > 10:
                metrics['sharpe'] *= 0.5 # Penalize
                metrics['reason'] = metrics.get('reason', "") + "HighTurnover;"

        # 2. Late Day Dependence
        # If > 70% of profit comes from trades closing after 15:00
        # Need exit times.
        exit_indices = trades['exit_idx'].values
        # Ensure indices are within bounds (engine handles it, but safety)
        valid_exits = exit_indices < len(df)
        exit_indices = exit_indices[valid_exits]

        if len(exit_indices) > 0:
            exit_times = df['datetime'].iloc[exit_indices].dt.time
            # 15:00
            cutoff = pd.Timestamp("15:00").time()

            is_late = np.array([t >= cutoff for t in exit_times])

            late_pnl = trades.loc[valid_exits][is_late]['net_return'].sum()
            total_pnl = trades['net_return'].sum()

            if total_pnl > 0 and late_pnl / total_pnl > 0.7:
                metrics['sharpe'] *= 0.7
                metrics['reason'] = metrics.get('reason', "") + "LateDayDependence;"
