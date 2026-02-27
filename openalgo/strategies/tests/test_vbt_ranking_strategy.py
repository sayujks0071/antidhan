import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import sys
import os

# Ensure the scripts directory is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

from vbt_ranking_strategy import run_backtest

class TestVBTRankingStrategy(unittest.TestCase):
    @patch('vbt_ranking_strategy.vbt.YFData.download')
    @patch('vbt_ranking_strategy.vbt.MA.run')
    @patch('vbt_ranking_strategy.vbt.Portfolio.from_signals')
    def test_run_backtest_premium(self, mock_from_signals, mock_ma_run, mock_yf_download):
        # Setup mock YFData
        mock_data = MagicMock()
        mock_data.get.return_value = pd.Series([100, 105, 110])
        mock_yf_download.return_value = mock_data

        # Setup mock MA
        mock_fast_ma = MagicMock()
        mock_fast_ma.ma_crossed_above.return_value = pd.Series([False, True, False])
        mock_fast_ma.ma_crossed_below.return_value = pd.Series([False, False, True])

        mock_slow_ma = MagicMock()

        # the run method is called twice, returning fast_ma then slow_ma
        mock_ma_run.side_effect = [mock_fast_ma, mock_slow_ma]

        # Setup mock Portfolio
        mock_portfolio = MagicMock()
        # Mock stats to return > 50% for Premium
        mock_portfolio.stats.return_value = {
            "Total Return [%]": 60.0,
            "Win Rate [%]": 55.0,
            "Max Drawdown [%]": 15.0,
            "Profit Factor": 2.5
        }
        mock_from_signals.return_value = mock_portfolio

        result = run_backtest(symbol="TEST_PREMIUM", fast_window=10, slow_window=50)

        self.assertIsNotNone(result)
        self.assertEqual(result["rank"], "Premium")
        self.assertEqual(result["total_return"], 60.0)

        # Verify ticker_kwargs was passed empty
        mock_yf_download.assert_called_once_with("TEST_PREMIUM", missing_index="drop", ticker_kwargs={})

    @patch('vbt_ranking_strategy.vbt.YFData.download')
    @patch('vbt_ranking_strategy.vbt.MA.run')
    @patch('vbt_ranking_strategy.vbt.Portfolio.from_signals')
    def test_run_backtest_moderate(self, mock_from_signals, mock_ma_run, mock_yf_download):
        mock_data = MagicMock()
        mock_data.get.return_value = pd.Series([100, 105, 110])
        mock_yf_download.return_value = mock_data

        mock_fast_ma = MagicMock()
        mock_slow_ma = MagicMock()
        mock_ma_run.side_effect = [mock_fast_ma, mock_slow_ma]

        mock_portfolio = MagicMock()
        mock_portfolio.stats.return_value = {
            "Total Return [%]": 25.0,
        }
        mock_from_signals.return_value = mock_portfolio

        result = run_backtest(symbol="TEST_MODERATE")

        self.assertIsNotNone(result)
        self.assertEqual(result["rank"], "Moderate")
        self.assertEqual(result["total_return"], 25.0)

    @patch('vbt_ranking_strategy.vbt.YFData.download')
    @patch('vbt_ranking_strategy.vbt.MA.run')
    @patch('vbt_ranking_strategy.vbt.Portfolio.from_signals')
    def test_run_backtest_low(self, mock_from_signals, mock_ma_run, mock_yf_download):
        mock_data = MagicMock()
        mock_data.get.return_value = pd.Series([100, 105, 110])
        mock_yf_download.return_value = mock_data

        mock_fast_ma = MagicMock()
        mock_slow_ma = MagicMock()
        mock_ma_run.side_effect = [mock_fast_ma, mock_slow_ma]

        mock_portfolio = MagicMock()
        mock_portfolio.stats.return_value = {
            "Total Return [%]": 5.0,
        }
        mock_from_signals.return_value = mock_portfolio

        result = run_backtest(symbol="TEST_LOW")

        self.assertIsNotNone(result)
        self.assertEqual(result["rank"], "Low")
        self.assertEqual(result["total_return"], 5.0)

    @patch('vbt_ranking_strategy.vbt.YFData.download')
    def test_run_backtest_missing_data(self, mock_yf_download):
        mock_data = MagicMock()
        mock_data.get.return_value = None
        mock_yf_download.return_value = mock_data

        result = run_backtest(symbol="TEST_EMPTY")

        self.assertIsNone(result)

    @patch('vbt_ranking_strategy.vbt.YFData.download')
    @patch('vbt_ranking_strategy.vbt.MA.run')
    @patch('vbt_ranking_strategy.vbt.Portfolio.from_signals')
    def test_run_backtest_with_dates(self, mock_from_signals, mock_ma_run, mock_yf_download):
        mock_data = MagicMock()
        mock_data.get.return_value = pd.Series([100, 105, 110])
        mock_yf_download.return_value = mock_data

        mock_fast_ma = MagicMock()
        mock_slow_ma = MagicMock()
        mock_ma_run.side_effect = [mock_fast_ma, mock_slow_ma]

        mock_portfolio = MagicMock()
        mock_portfolio.stats.return_value = {"Total Return [%]": 100.0}
        mock_from_signals.return_value = mock_portfolio

        result = run_backtest(symbol="TEST_DATES", start_date="2023-01-01", end_date="2023-12-31")

        self.assertIsNotNone(result)

        # Verify ticker_kwargs was passed with dates
        mock_yf_download.assert_called_once_with(
            "TEST_DATES",
            missing_index="drop",
            ticker_kwargs={'start': '2023-01-01', 'end': '2023-12-31'}
        )

if __name__ == '__main__':
    unittest.main()
