import unittest
import pandas as pd
import numpy as np
import sys
import os

# Add repo root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from openalgo.strategies.scripts.gap_fade_strategy import GapFadeStrategy
except ImportError:
    # Handle direct execution imports if needed
    pass

class TestGapFadeStrategy(unittest.TestCase):
    def setUp(self):
        self.strategy = GapFadeStrategy()

    def test_import_and_init(self):
        self.assertIsInstance(self.strategy, GapFadeStrategy)

    def test_signal_generation(self):
        # Create Dummy DataFrame
        df = pd.DataFrame({
            'close': np.random.rand(100) * 100 + 100,
            'high': np.random.rand(100) * 105 + 100,
            'low': np.random.rand(100) * 95 + 100,
            'open': np.random.rand(100) * 100 + 100,
            'volume': np.random.rand(100) * 1000
        })

        signal, qty, details = self.strategy.generate_signal_internal(df)
        self.assertIn(signal, ["BUY", "SELL", "HOLD"])

if __name__ == '__main__':
    unittest.main()
