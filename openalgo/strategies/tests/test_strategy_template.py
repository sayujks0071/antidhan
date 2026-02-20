import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

# Adjust path to allow importing the strategy template from scripts/
current_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(current_dir)
scripts_dir = os.path.join(strategies_dir, 'scripts')
utils_dir = os.path.join(strategies_dir, 'utils')

# Ensure utils are importable for the strategy template if it needs them
# (The template modifies sys.path itself, but we help it out just in case)
if utils_dir not in sys.path:
    sys.path.insert(0, utils_dir)

# Ensure scripts are importable so we can import strategy_template
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

# Mock environment variable to prevent APIKey errors during import if checked
os.environ['OPENALGO_APIKEY'] = 'dummy_key'

# Now import the module
import strategy_template

class TestStrategyTemplate(unittest.TestCase):
    def setUp(self):
        # Create a dummy DataFrame with enough data (needs > 50 rows per logic)
        dates = pd.date_range(start='2023-01-01', periods=60, freq='5min')
        self.df = pd.DataFrame({
            'open': [100.0 + i*0.1 for i in range(60)],
            'high': [101.0 + i*0.1 for i in range(60)],
            'low': [99.0 + i*0.1 for i in range(60)],
            'close': [100.5 + i*0.1 for i in range(60)],
            'volume': [1000 + i for i in range(60)]
        }, index=dates)

    def test_generate_signal_structure(self):
        """Test that generate_signal returns the correct structure."""
        action, score, details = strategy_template.generate_signal(self.df)

        self.assertIn(action, ['BUY', 'SELL', 'HOLD'])
        self.assertIsInstance(score, float)
        self.assertIsInstance(details, dict)

        # Check mandatory details
        self.assertIn('atr', details)
        self.assertIn('quantity', details)
        self.assertIn('sl', details)
        self.assertIn('tp', details)
        self.assertIn('breakeven_trigger_r', details)
        self.assertIn('time_stop_bars', details)

        # Verify values are reasonable
        self.assertTrue(details['quantity'] >= 1)
        self.assertTrue(details['atr'] >= 0)

    def test_generate_signal_empty_df(self):
        """Test graceful handling of empty DataFrame."""
        action, score, details = strategy_template.generate_signal(pd.DataFrame())
        self.assertEqual(action, 'HOLD')
        self.assertEqual(score, 0.0)
        self.assertEqual(details, {})

    def test_generate_signal_short_df(self):
        """Test graceful handling of DataFrame with insufficient data."""
        short_df = self.df.head(10)
        action, score, details = strategy_template.generate_signal(short_df)
        self.assertEqual(action, 'HOLD')
        self.assertEqual(score, 0.0)
        self.assertEqual(details, {})

    @patch('strategy_template.BaseStrategy.__init__', return_value=None)
    def test_instantiation(self, mock_init):
        """Test that the strategy class can be instantiated."""
        # We verify that we can create the object and it initializes its state
        strategy = strategy_template.YourStrategy(symbol='SBIN', quantity=10)

        # Manually call super init if we mocked it out completely,
        # or just check the local state initialization
        # Since we mocked BaseStrategy.__init__, we need to be careful.
        # Ideally we let it run if BaseStrategy is robust.
        # But BaseStrategy might try to connect to things.

        # Let's check state attributes set in subclass
        self.assertEqual(strategy.trailing_stop, 0.0)
        self.assertEqual(strategy.bars_in_trade, 0)
        self.assertFalse(strategy.partial_exit_done)

if __name__ == '__main__':
    unittest.main()
