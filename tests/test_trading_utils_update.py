import unittest
import pandas as pd
import numpy as np
import sys
import os

# Add openalgo directory to path so 'utils' can be imported
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

from strategies.utils.trading_utils import calculate_bollinger_bands, normalize_symbol

class TestTradingUtilsUpdate(unittest.TestCase):
    def test_calculate_bollinger_bands(self):
        data = pd.Series([100, 102, 104, 103, 105, 107, 106, 108, 110, 109] * 5) # 50 points
        sma, upper, lower = calculate_bollinger_bands(data, window=20, num_std=2)

        self.assertEqual(len(sma), 50)
        self.assertTrue(pd.isna(sma.iloc[18])) # First 19 are NaN (0-18)
        self.assertFalse(pd.isna(sma.iloc[19]))

        # Check calculation for index 19
        window = data.iloc[0:20]
        expected_mean = window.mean()
        expected_std = window.std()

        self.assertAlmostEqual(sma.iloc[19], expected_mean)
        self.assertAlmostEqual(upper.iloc[19], expected_mean + 2 * expected_std)
        self.assertAlmostEqual(lower.iloc[19], expected_mean - 2 * expected_std)

    def test_normalize_symbol(self):
        self.assertEqual(normalize_symbol("NIFTY 50"), "NIFTY")
        self.assertEqual(normalize_symbol("NIFTY BANK"), "BANKNIFTY")
        self.assertEqual(normalize_symbol("RELIANCE"), "RELIANCE")

if __name__ == '__main__':
    unittest.main()
