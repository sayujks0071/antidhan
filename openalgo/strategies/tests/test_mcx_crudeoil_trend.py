import sys
import os
import pandas as pd
import unittest
import numpy as np

# Add strategies/scripts directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(current_dir)
scripts_dir = os.path.join(strategies_dir, "scripts")
sys.path.insert(0, scripts_dir)

# Add openalgo directory to path so 'import utils' works (for trading_utils)
openalgo_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, openalgo_dir)

# Add strategies dir for utils resolution within the script (if needed)
sys.path.insert(0, strategies_dir)

import mcx_crudeoil_trend_strategy

class TestMCXCrudeOilTrend(unittest.TestCase):
    def test_import(self):
        self.assertTrue('mcx_crudeoil_trend_strategy' in sys.modules)

    def test_generate_signal_buy(self):
        # Create dummy data for BUY condition
        # Trend Up: Close > EMA20
        # RSI > 50

        # Linear uptrend
        prices = np.linspace(100, 200, 100)

        data = {
            "close": prices,
            "high": prices + 2,
            "low": prices - 2,
            "open": prices
        }
        df = pd.DataFrame(data)

        signal, confidence, metadata = mcx_crudeoil_trend_strategy.generate_signal(df)

        self.assertEqual(signal, "BUY")
        self.assertEqual(metadata.get("reason"), "Trend Long")

    def test_generate_signal_sell(self):
        # Create dummy data for SELL condition
        # Trend Down: Close < EMA20
        # RSI < 50

        # Linear downtrend
        prices = np.linspace(200, 100, 100)

        data = {
            "close": prices,
            "high": prices + 2,
            "low": prices - 2,
            "open": prices
        }
        df = pd.DataFrame(data)

        signal, confidence, metadata = mcx_crudeoil_trend_strategy.generate_signal(df)

        self.assertEqual(signal, "SELL")
        self.assertEqual(metadata.get("reason"), "Trend Short")

    def test_insufficient_data(self):
        prices = np.linspace(100, 110, 10) # Only 10 points
        data = {
            "close": prices,
            "high": prices + 1,
            "low": prices - 1,
            "open": prices
        }
        df = pd.DataFrame(data)

        signal, confidence, metadata = mcx_crudeoil_trend_strategy.generate_signal(df)
        self.assertEqual(signal, "HOLD")

if __name__ == '__main__':
    unittest.main()
