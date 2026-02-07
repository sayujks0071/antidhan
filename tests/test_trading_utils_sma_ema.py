
import unittest
import pandas as pd
import numpy as np
import sys
import os

# Add openalgo directory to path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

from strategies.utils.trading_utils import calculate_sma, calculate_ema

class TestTradingUtilsSMAEMA(unittest.TestCase):
    def test_calculate_sma(self):
        data = pd.Series([10, 20, 30, 40, 50])
        sma = calculate_sma(data, period=3)
        # Expected:
        # 0: NaN
        # 1: NaN
        # 2: (10+20+30)/3 = 20
        # 3: (20+30+40)/3 = 30
        # 4: (30+40+50)/3 = 40
        self.assertTrue(pd.isna(sma.iloc[0]))
        self.assertTrue(pd.isna(sma.iloc[1]))
        self.assertEqual(sma.iloc[2], 20.0)
        self.assertEqual(sma.iloc[3], 30.0)
        self.assertEqual(sma.iloc[4], 40.0)

    def test_calculate_ema(self):
        data = pd.Series([10, 20, 30, 40, 50])
        # pandas ewm span=3, adjust=False
        # alpha = 2 / (3 + 1) = 0.5
        # EMA_0 = 10
        # EMA_1 = 10 + 0.5 * (20 - 10) = 15
        # EMA_2 = 15 + 0.5 * (30 - 15) = 22.5
        # EMA_3 = 22.5 + 0.5 * (40 - 22.5) = 31.25
        # EMA_4 = 31.25 + 0.5 * (50 - 31.25) = 40.625
        ema = calculate_ema(data, period=3)

        self.assertEqual(ema.iloc[0], 10.0)
        self.assertEqual(ema.iloc[1], 15.0)
        self.assertEqual(ema.iloc[2], 22.5)
        self.assertEqual(ema.iloc[3], 31.25)
        self.assertEqual(ema.iloc[4], 40.625)

if __name__ == '__main__':
    unittest.main()
