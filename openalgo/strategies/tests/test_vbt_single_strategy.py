import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
import sys
import os

# Add scripts directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))

from vbt_single_strategy import get_rank, run_strategy, RANKING

class TestVbtSingleStrategy(unittest.TestCase):

    def test_ranking_logic(self):
        # Premium: Sharpe > 1.5 and Return > 50%
        self.assertEqual(get_rank(1.6, 51.0), "Premium")
        self.assertEqual(get_rank(2.0, 100.0), "Premium")

        # Moderate: Sharpe > 0.8 and Return > 0%
        self.assertEqual(get_rank(1.4, 49.0), "Moderate") # High Sharpe, Low Return -> Moderate

        self.assertEqual(get_rank(0.9, 10.0), "Moderate")

        # Low cases
        self.assertEqual(get_rank(0.7, 10.0), "Low") # Low Sharpe
        self.assertEqual(get_rank(1.0, -5.0), "Low") # Negative Return
        self.assertEqual(get_rank(0.5, -10.0), "Low")

    @patch('vectorbt.YFData.download')
    def test_backtest_execution(self, mock_download):
        # Create synthetic data
        dates = pd.date_range(start='2020-01-01', periods=100, freq='D')
        # Create a price series that trends up nicely to ensure some profit
        price_values = np.linspace(100, 200, 100) + np.sin(np.linspace(0, 10, 100)) * 5
        price_series = pd.Series(price_values, index=dates, name="Close")

        # Mock the return value of download().get()
        mock_data = MagicMock()
        mock_data.get.return_value = price_series
        mock_download.return_value = mock_data

        # Run strategy
        result = run_strategy(symbol="TEST-USD")

        # Assertions
        self.assertIsNotNone(result)
        self.assertEqual(result['symbol'], "TEST-USD")
        self.assertIsInstance(result['total_return'], float)
        self.assertIsInstance(result['sharpe'], float)
        self.assertIn(result['rank'], ["Premium", "Moderate", "Low"])

        # Verify download was called
        mock_download.assert_called_once()

    @patch('vectorbt.YFData.download')
    def test_backtest_fallback(self, mock_download):
        # Simulate exception during download
        mock_download.side_effect = Exception("Connection Error")

        # Run strategy - should handle exception and use synthetic data
        with patch('builtins.print') as mock_print:
            result = run_strategy(symbol="FAIL-USD")

        self.assertIsNotNone(result)
        self.assertEqual(result['symbol'], "FAIL-USD")
