import os
import sys
import unittest
from unittest.mock import MagicMock

import pandas as pd

# Add scripts directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(current_dir)
scripts_dir = os.path.join(strategies_dir, "scripts")
sys.path.insert(0, scripts_dir)

# Add openalgo directory to path so 'import utils' works (for trading_utils)
openalgo_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, openalgo_dir)

# Add strategies dir for utils resolution within the script (if needed)
sys.path.insert(0, strategies_dir)

import mcx_silver_momentum


class TestMCXSilverMomentum(unittest.TestCase):
    def test_import(self):
        self.assertTrue('mcx_silver_momentum' in sys.modules)

    def test_generate_signal_buy(self):
        # Create dummy data
        # SMA 50 calculation requires 50 periods.
        # We need > 50 rows.
        prices = [100 + i for i in range(60)]
        data = {
            "close": prices,
            "high": [p + 2 for p in prices],
            "low": [p - 2 for p in prices],
            "open": prices
        }
        df = pd.DataFrame(data)

        signal, confidence, metadata = mcx_silver_momentum.generate_signal(df)
        self.assertEqual(signal, "BUY")

    def test_generate_signal_sell(self):
        # Falling trend
        prices = [200 - i for i in range(60)]
        data = {
            "close": prices,
            "high": [p + 2 for p in prices],
            "low": [p - 2 for p in prices],
            "open": prices
        }
        df = pd.DataFrame(data)

        signal, confidence, metadata = mcx_silver_momentum.generate_signal(df)
        self.assertEqual(signal, "SELL")

if __name__ == '__main__':
    unittest.main()
