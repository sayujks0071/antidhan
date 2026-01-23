import unittest
import pandas as pd
import numpy as np
from packages.strategy_foundry.backtest.engine import BacktestEngine
from packages.strategy_foundry.factory.grammar import StrategyConfig, Rule
from packages.strategy_foundry.factory.generator import StrategyGenerator

class TestEngine(unittest.TestCase):
    def setUp(self):
        # Create dummy data
        dates = pd.date_range(start='2023-01-01', periods=100)
        self.df = pd.DataFrame({
            'datetime': dates,
            'open': np.linspace(100, 200, 100),
            'high': np.linspace(105, 205, 100),
            'low': np.linspace(95, 195, 100),
            'close': np.linspace(102, 202, 100),
            'volume': 1000
        })

    def test_run_simple_strategy(self):
        # Create a simple strategy: Always Long (Rule: Close > 0)
        rule = Rule(
            indicator='ema', # Fake it
            operator='>',
            value='close',
            params={'period': 10}
        )
        # Actually logic in generator: if ema > close.
        # Let's make a condition that is mostly True.
        # Donchian: Close > Lower.

        # Or just specific EMA logic.

        config = StrategyConfig(
            strategy_id="test",
            entry_rules=[rule],
            exit_rules=[],
            stop_loss_atr=10.0, # Wide stop
            take_profit_atr=10.0,
            max_bars_hold=5
        )

        engine = BacktestEngine(self.df)
        res = engine.run(config)

        self.assertIn('equity_curve', res)
        self.assertIn('trades', res)
        self.assertFalse(res['equity_curve'].empty)

if __name__ == '__main__':
    unittest.main()
