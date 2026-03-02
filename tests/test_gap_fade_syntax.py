import sys
import os
import unittest

# Add repo root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from openalgo.strategies.scripts.gap_fade_strategy import GapFadeStrategy
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

class TestGapFadeStrategy(unittest.TestCase):
    def test_instantiation(self):
        try:
            strategy = GapFadeStrategy(symbol="NIFTY", api_key="test_key", ignore_time=True)
            self.assertIsNotNone(strategy)
            print("GapFadeStrategy instantiated successfully.")
        except Exception as e:
            self.fail(f"GapFadeStrategy instantiation failed: {e}")

if __name__ == "__main__":
    unittest.main()
