import unittest
import pandas as pd
import numpy as np
import sys
import os

# Add openalgo directory to path so 'utils' can be imported
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

from strategies.utils.trading_utils import calculate_sma, calculate_ema, calculate_relative_strength

class TestTradingUtilsAdditions(unittest.TestCase):
    def test_calculate_sma(self):
        data = pd.Series([1, 2, 3, 4, 5])
        sma = calculate_sma(data, period=3)
        # Expected: [NaN, NaN, 2.0, 3.0, 4.0]
        self.assertTrue(pd.isna(sma.iloc[1]))
        self.assertEqual(sma.iloc[2], 2.0)
        self.assertEqual(sma.iloc[4], 4.0)

    def test_calculate_ema(self):
        data = pd.Series([10, 10, 10, 10, 10])
        ema = calculate_ema(data, period=2)
        # EMA of constant series should be constant
        self.assertEqual(ema.iloc[4], 10.0)

        data2 = pd.Series([10, 11, 12])
        ema2 = calculate_ema(data2, period=2)
        # First value = 10
        # Second value = (11 - 10) * (2/(2+1)) + 10 = 1 * 2/3 + 10 = 10.666...
        # Wait, pandas ewm span=2 uses alpha=2/(span+1) = 2/3?
        # Pandas uses alpha = 2/(span+1) by default if adjust=False?
        # calculate_ema uses span=period, adjust=False.
        # alpha = 2 / (2 + 1) = 2/3.
        # EMA_t = alpha * x_t + (1-alpha) * EMA_{t-1}
        # EMA_0 = 10
        # EMA_1 = (2/3)*11 + (1/3)*10 = 7.33 + 3.33 = 10.666
        # Let's just check it's not NaN and follows trend
        self.assertFalse(pd.isna(ema2.iloc[0]))
        self.assertTrue(ema2.iloc[2] > ema2.iloc[1] > ema2.iloc[0])

    def test_calculate_relative_strength(self):
        df = pd.DataFrame({'close': [100, 110]}) # +10%
        index_df = pd.DataFrame({'close': [1000, 1050]}) # +5%

        # Period=1.
        # Stock ROC = (110-100)/100 = 0.10
        # Index ROC = (1050-1000)/1000 = 0.05
        # RS = 0.10 - 0.05 = 0.05

        rs = calculate_relative_strength(df, index_df, period=1)
        self.assertAlmostEqual(rs, 0.05)

        # Test empty index
        rs_empty = calculate_relative_strength(df, pd.DataFrame(), period=1)
        self.assertEqual(rs_empty, 0.0)

if __name__ == '__main__':
    unittest.main()
