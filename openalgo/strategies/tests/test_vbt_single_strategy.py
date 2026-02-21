import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
import sys
import os

# Ensure the module can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from openalgo.strategies.scripts.vbt_single_strategy import backtest_strategy

class TestVBTSingleStrategy(unittest.TestCase):
    @patch('openalgo.strategies.scripts.vbt_single_strategy.vbt.YFData.download')
    def test_backtest_strategy_mocked(self, mock_download):
        # Create a mock price series (linear uptrend to ensure positive return)
        dates = pd.date_range(start='2024-01-01', periods=100)
        price = pd.Series(np.linspace(100, 200, 100), index=dates)

        # Configure the mock to return an object with a .get() method
        mock_data = MagicMock()
        mock_data.get.return_value = price
        mock_download.return_value = mock_data

        # Run the function
        # fast=10, slow=20 to generate signals
        rank = backtest_strategy(symbol="TEST", fast_window=10, slow_window=20, start_date="2024-01-01")

        # Verify it returns a valid rank
        self.assertIn(rank, ["Premium", "Moderate", "Low"])

        # Verify download was called
        mock_download.assert_called()

if __name__ == '__main__':
    unittest.main()
