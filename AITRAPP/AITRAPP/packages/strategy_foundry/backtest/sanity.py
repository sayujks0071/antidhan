import pandas as pd
import logging
from typing import Dict
from packages.strategy_foundry.backtest.engine import BacktestEngine
from packages.strategy_foundry.backtest.metrics import MetricCalculator
from packages.strategy_foundry.factory.grammar import StrategyConfig
from packages.strategy_foundry.adapters.core_costs import CostModel

logger = logging.getLogger(__name__)

class SanityChecker:
    def __init__(self, df_daily: pd.DataFrame, cost_model: CostModel):
        self.df_daily = df_daily
        self.cost_model = cost_model
        self.engine = BacktestEngine(self.cost_model)

    def check(self, config: StrategyConfig) -> Dict:
        """
        Runs the strategy on Daily data and checks for catastrophic failure.
        Returns metrics and a 'passed' boolean.
        """
        if self.df_daily is None or self.df_daily.empty:
            logger.warning("No daily data for sanity check. Skipping.")
            return {"passed": True, "reason": "NoData"}

        # Run on Daily
        trades = self.engine.run(self.df_daily, config)

        # Calculate Metrics (Full history)
        start_date = self.df_daily['datetime'].iloc[0]
        end_date = self.df_daily['datetime'].iloc[-1]
        years = (end_date - start_date).days / 365.25
        if years < 0.01: years = 0.01

        metrics = MetricCalculator.compute(trades, years)

        # Check Thresholds
        passed = True
        reason = ""

        # Thresholds
        # Sharpe < -0.5 (Aligned with foundry.yaml)
        # MaxDD > 45%

        if metrics['sharpe'] < -0.5:
            passed = False
            reason += "DailySharpeTooLow;"

        if metrics['max_dd'] > 0.45:
            passed = False
            reason += "DailyDDTooHigh;"

        return {
            "passed": passed,
            "reason": reason,
            "daily_sharpe": metrics['sharpe'],
            "daily_max_dd": metrics['max_dd']
        }
