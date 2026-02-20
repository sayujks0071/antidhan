import unittest
import pandas as pd
import numpy as np
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from openalgo.strategies.utils.trading_utils import (
    calculate_mfi, calculate_cci, calculate_vwmacd, calculate_adx_di
)

class TestNewIndicators(unittest.TestCase):
    def setUp(self):
        # Create a sample DataFrame
        np.random.seed(42)
        self.df = pd.DataFrame({
            'high': np.random.rand(100) * 100 + 100,
            'low': np.random.rand(100) * 100 + 90,
            'close': np.random.rand(100) * 100 + 95,
            'volume': np.random.randint(1000, 10000, 100)
        })
        # Ensure high is highest, low is lowest
        self.df['high'] = self.df[['high', 'low', 'close']].max(axis=1)
        self.df['low'] = self.df[['high', 'low', 'close']].min(axis=1)

    def test_calculate_mfi(self):
        mfi = calculate_mfi(self.df)
        self.assertIsInstance(mfi, pd.Series)
        self.assertEqual(len(mfi), len(self.df))
        # Handle NaN values for initial period by filling or dropping
        mfi_clean = mfi.dropna()
        if not mfi_clean.empty:
            self.assertTrue((mfi_clean >= 0).all() and (mfi_clean <= 100).all())

    def test_calculate_cci(self):
        cci = calculate_cci(self.df)
        self.assertIsInstance(cci, pd.Series)
        self.assertEqual(len(cci), len(self.df))

    def test_calculate_vwmacd(self):
        macd, signal, hist = calculate_vwmacd(self.df)
        self.assertIsInstance(macd, pd.Series)
        self.assertIsInstance(signal, pd.Series)
        self.assertIsInstance(hist, pd.Series)
        self.assertEqual(len(macd), len(self.df))

    def test_calculate_adx_di(self):
        adx, plus_di, minus_di = calculate_adx_di(self.df)
        self.assertIsInstance(adx, pd.Series)
        self.assertIsInstance(plus_di, pd.Series)
        self.assertIsInstance(minus_di, pd.Series)
        self.assertEqual(len(adx), len(self.df))

if __name__ == '__main__':
    unittest.main()
