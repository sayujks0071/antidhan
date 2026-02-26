import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import pandas as pd
import numpy as np
import importlib.util
import vectorbt as vbt # Ensure vectorbt is imported for patching

# Load the strategy module dynamically
MODULE_PATH = os.path.join(os.path.dirname(__file__), '../scripts/vbt_ranking_strategy.py')
spec = importlib.util.spec_from_file_location("vbt_ranking_strategy", MODULE_PATH)
vbt_strategy = importlib.util.module_from_spec(spec)
sys.modules["vbt_ranking_strategy"] = vbt_strategy
spec.loader.exec_module(vbt_strategy)

class TestVbtRankingStrategy(unittest.TestCase):

    def test_rank_strategy(self):
        # Test Premium
        stats_premium = {'Sharpe Ratio': 2.0, 'Total Return [%]': 60}
        self.assertEqual(vbt_strategy.rank_strategy(stats_premium), "Premium")

        # Test Moderate
        stats_moderate = {'Sharpe Ratio': 1.0, 'Total Return [%]': 10}
        self.assertEqual(vbt_strategy.rank_strategy(stats_moderate), "Moderate")

        # Test Low
        stats_low = {'Sharpe Ratio': 0.5, 'Total Return [%]': -5}
        self.assertEqual(vbt_strategy.rank_strategy(stats_low), "Low")

    @patch('vectorbt.YFData.download')
    @patch('vectorbt.Portfolio.from_signals')
    @patch('vectorbt.MA.run')
    def test_run_backtest_mock(self, mock_ma_run, mock_portfolio, mock_download):
        # Setup mocks
        mock_data = MagicMock()
        mock_price = pd.Series(np.random.rand(100), index=pd.date_range('2023-01-01', periods=100))
        mock_data.get.return_value = mock_price
        mock_download.return_value = mock_data

        mock_ma = MagicMock()
        mock_ma_run.return_value = mock_ma
        mock_ma.ma_crossed_above.return_value = pd.Series([False]*100)
        mock_ma.ma_crossed_below.return_value = pd.Series([False]*100)

        mock_pf = MagicMock()
        mock_portfolio.return_value = mock_pf
        mock_pf.stats.return_value = {'Sharpe Ratio': 1.6, 'Total Return [%]': 55}
        mock_pf.plot.return_value = MagicMock() # Mock the plot object

        # Run
        rank, stats = vbt_strategy.run_backtest("BTC-USD")

        # Verify ticker_kwargs was passed
        mock_download.assert_called_with(
            "BTC-USD",
            period="1y",
            missing_index='drop',
            ticker_kwargs={}
        )

        self.assertEqual(rank, "Premium")

    @patch('vectorbt.YFData.download')
    @patch('vectorbt.Portfolio.from_signals')
    @patch('vectorbt.MA.run')
    def test_run_backtest_fallback(self, mock_ma_run, mock_portfolio, mock_download):
        # Mock download failure
        mock_download.side_effect = Exception("Mock download error")

        mock_ma = MagicMock()
        mock_ma_run.return_value = mock_ma
        mock_ma.ma_crossed_above.return_value = pd.Series([False]*365)
        mock_ma.ma_crossed_below.return_value = pd.Series([False]*365)

        mock_pf = MagicMock()
        mock_portfolio.return_value = mock_pf
        mock_pf.stats.return_value = {'Sharpe Ratio': 0.5, 'Total Return [%]': -5}
        mock_pf.plot.return_value = MagicMock()

        # Run
        rank, stats = vbt_strategy.run_backtest("BTC-USD")

        self.assertEqual(rank, "Low")

if __name__ == '__main__':
    unittest.main()
