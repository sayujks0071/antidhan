import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from openalgo.strategies.scripts.nse_intraday_momentum import NSEIntradayMomentum

class TestNSEMomentumLogic(unittest.TestCase):
    def setUp(self):
        self.strategy = NSEIntradayMomentum(
            symbol='TEST',
            api_key='dummy',
            port=5001
        )
        # Suppress logging
        self.strategy.logger = MagicMock()

    @patch('openalgo.strategies.scripts.nse_intraday_momentum.calculate_rsi')
    @patch('openalgo.strategies.scripts.nse_intraday_momentum.calculate_macd')
    @patch('openalgo.strategies.scripts.nse_intraday_momentum.calculate_supertrend')
    def test_buy_signal(self, mock_st, mock_macd, mock_rsi):
        # Mock Data
        df = pd.DataFrame({
            'close': [100.0] * 50,
            'high': [105.0] * 50,
            'low': [95.0] * 50,
            'open': [100.0] * 50,
            'volume': [1000] * 50
        })

        # Mock Indicators for BUY
        # RSI > 55
        mock_rsi.return_value = pd.Series([60.0] * 50, index=df.index)

        # MACD > Signal
        macd_line = pd.Series([1.5] * 50, index=df.index)
        signal_line = pd.Series([1.0] * 50, index=df.index)
        hist = pd.Series([0.5] * 50, index=df.index)
        mock_macd.return_value = (macd_line, signal_line, hist)

        # SuperTrend < Close (Bullish) => Close > SuperTrend
        # Close is 100, so SuperTrend should be < 100, e.g., 90
        st_series = pd.Series([90.0] * 50, index=df.index)
        direction = pd.Series([1] * 50, index=df.index) # 1 for Up
        mock_st.return_value = (st_series, direction)

        signal, confidence, meta = self.strategy.calculate_signal(df)

        self.assertEqual(signal, 'BUY')
        self.assertEqual(meta['reason'], 'entry_long')

    @patch('openalgo.strategies.scripts.nse_intraday_momentum.calculate_rsi')
    @patch('openalgo.strategies.scripts.nse_intraday_momentum.calculate_macd')
    @patch('openalgo.strategies.scripts.nse_intraday_momentum.calculate_supertrend')
    def test_sell_signal(self, mock_st, mock_macd, mock_rsi):
        # Mock Data
        df = pd.DataFrame({
            'close': [100.0] * 50,
            'high': [105.0] * 50,
            'low': [95.0] * 50,
            'open': [100.0] * 50,
            'volume': [1000] * 50
        })

        # Mock Indicators for SELL
        # RSI < 45
        mock_rsi.return_value = pd.Series([40.0] * 50, index=df.index)

        # MACD < Signal
        macd_line = pd.Series([0.5] * 50, index=df.index)
        signal_line = pd.Series([1.0] * 50, index=df.index)
        hist = pd.Series([-0.5] * 50, index=df.index)
        mock_macd.return_value = (macd_line, signal_line, hist)

        # SuperTrend > Close (Bearish) => Close < SuperTrend
        # Close is 100, so SuperTrend should be > 100, e.g., 110
        st_series = pd.Series([110.0] * 50, index=df.index)
        direction = pd.Series([-1] * 50, index=df.index) # -1 for Down
        mock_st.return_value = (st_series, direction)

        signal, confidence, meta = self.strategy.calculate_signal(df)

        self.assertEqual(signal, 'SELL')
        self.assertEqual(meta['reason'], 'entry_short')

    def test_hold_signal(self):
        # Test empty or short dataframe
        df = pd.DataFrame()
        signal, _, _ = self.strategy.calculate_signal(df)
        self.assertEqual(signal, 'HOLD')

if __name__ == '__main__':
    unittest.main()
