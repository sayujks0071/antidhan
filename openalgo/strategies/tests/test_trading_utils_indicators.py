import unittest
import pandas as pd
import numpy as np
import sys
import os

# Add utils to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../utils')))

from trading_utils import calculate_rsi, calculate_atr

class TestTradingUtilsIndicators(unittest.TestCase):
    def test_calculate_rsi(self):
        # Create enough data for RSI 14
        data = list(range(100))
        df = pd.DataFrame({'close': data})
        df = calculate_rsi(df, period=14)
        self.assertIn('rsi', df.columns)
        self.assertFalse(df['rsi'].iloc[-1] == np.nan)

    def test_calculate_atr(self):
        # Create enough data for ATR 14
        data_len = 50
        df = pd.DataFrame({
            'high': [10 + i for i in range(data_len)],
            'low': [9 + i for i in range(data_len)],
            'close': [9.5 + i for i in range(data_len)]
        })
        df = calculate_atr(df, period=14)
        self.assertIn('atr', df.columns)
        self.assertFalse(df['atr'].iloc[-1] == np.nan)

if __name__ == '__main__':
    unittest.main()
