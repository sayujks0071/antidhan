import unittest

import pandas as pd

from packages.strategy_foundry.backtest.metrics import MetricsCalculator


class TestMetrics(unittest.TestCase):
    def test_calculate(self):
        equity = pd.Series([100, 101, 102, 105, 104, 110], index=pd.date_range('2023-01-01', periods=6))
        trades = pd.DataFrame([
            {'pnl': 5},
            {'pnl': -1},
            {'pnl': 6}
        ])

        m = MetricsCalculator.calculate(equity, trades)

        self.assertAlmostEqual(m['total_return'], 0.10)
        self.assertEqual(m['trades'], 3)
        self.assertGreater(m['cagr'], 0)

if __name__ == '__main__':
    unittest.main()
