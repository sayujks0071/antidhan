import unittest
import pandas as pd
import numpy as np
import sys
import os

# Add openalgo directory to path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

from strategies.utils.trading_utils import calculate_macd

class TestTradingUtilsMACD(unittest.TestCase):
    def test_calculate_macd(self):
        # Create sample data
        data = pd.Series([10, 11, 12, 13, 14, 15, 14, 13, 12, 11, 10] * 5)

        macd, signal, hist = calculate_macd(data, fast=12, slow=26, signal=9)

        # Check types
        self.assertIsInstance(macd, pd.Series)
        self.assertIsInstance(signal, pd.Series)
        self.assertIsInstance(hist, pd.Series)

        # Check lengths
        self.assertEqual(len(macd), len(data))
        self.assertEqual(len(signal), len(data))
        self.assertEqual(len(hist), len(data))

        # Check calculation (basic sanity check - first value is usually 0 diff for MACD if adjust=False logic starts same)
        # But EWM behavior depends.
        # Just ensure it runs without error and returns numbers.
        self.assertFalse(macd.isnull().all())

if __name__ == '__main__':
    unittest.main()
