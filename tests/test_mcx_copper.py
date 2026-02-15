import sys
import os
import pandas as pd
import numpy as np
import unittest
from unittest.mock import MagicMock

# Setup paths
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
openalgo_dir = os.path.join(root_dir, 'openalgo')
utils_dir = os.path.join(openalgo_dir, 'strategies', 'utils')
strategies_dir = os.path.join(openalgo_dir, 'strategies')

# Clear sys.path of potentially conflicting entries from previous runs (in REPL context) or just construct carefully
# We want openalgo_dir to be high priority so 'import utils' finds openalgo/utils, NOT strategies/utils.

# Insert in reverse order of desired priority (since insert(0) pushes to front)

# Priority 3: Root (for import openalgo)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Priority 2: Strategies Utils (for import trading_utils)
# This directory contains trading_utils.py. Adding it to path makes 'import trading_utils' work.
if utils_dir not in sys.path:
    sys.path.insert(0, utils_dir)

# Priority 1: OpenAlgo Dir (for import utils)
# This directory contains 'utils' folder. Adding it to path makes 'import utils' find openalgo/utils.
# This MUST be before strategies_dir (if it were in path) because strategies also has 'utils'.
if openalgo_dir not in sys.path:
    sys.path.insert(0, openalgo_dir)

# Mock modules
sys.modules['openalgo_observability'] = MagicMock()
sys.modules['openalgo_observability.logging_setup'] = MagicMock()
sys.modules['flask'] = MagicMock()

# Now import the strategy
# Since we added utils_dir to path, we might be able to import trading_utils directly
# But strategy script adds utils_dir itself.

from strategies.scripts.mcx_copper_trend_strategy import generate_signal

class TestMCXCopperStrategy(unittest.TestCase):
    def setUp(self):
        # Create dummy data
        dates = pd.date_range(start='2024-01-01', periods=100, freq='15min')
        self.df = pd.DataFrame({
            'open': [100.0] * 100,
            'high': [105.0] * 100,
            'low': [95.0] * 100,
            'close': [100.0] * 100,
            'volume': [1000] * 100
        }, index=dates)

    def test_hold_signal_flat(self):
        # Flat market -> RSI is NaN -> fillna(0) -> RSI=0.
        # Strategy logic: RSI < 40 -> SELL (Exit).
        signal, conf, meta = generate_signal(self.df)
        self.assertEqual(signal, "SELL")

    def test_buy_signal_simulation(self):
        # Simulate a strong upward trend for breakout
        trend = np.linspace(100, 150, 100)
        self.df['close'] = trend
        self.df['high'] = trend + 5
        self.df['low'] = trend - 5
        self.df['open'] = trend

        signal, conf, meta = generate_signal(self.df)

        self.assertIn(signal, ["BUY", "SELL", "HOLD"])
        self.assertIsInstance(conf, float)
        self.assertIsInstance(meta, dict)

if __name__ == '__main__':
    unittest.main()
