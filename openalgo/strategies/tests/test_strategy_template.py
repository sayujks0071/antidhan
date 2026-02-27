import os
import sys
import unittest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

# Import the strategy module dynamically since it might not be in the python path directly
import importlib.util
spec = importlib.util.spec_from_file_location(
    "strategy_template",
    os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts/strategy_template.py'))
)
strategy_template = importlib.util.module_from_spec(spec)
sys.modules["strategy_template"] = strategy_template
spec.loader.exec_module(strategy_template)

class TestStrategyTemplate(unittest.TestCase):
    def setUp(self):
        self.symbol = "NIFTY"
        self.strategy = strategy_template.YourStrategy(symbol=self.symbol)

        # Mock API Client
        self.strategy.client = MagicMock()
        self.strategy.pm = MagicMock()
        self.strategy.smart_order = MagicMock()

    def test_initialization(self):
        """Test if strategy initializes correctly with default parameters."""
        self.assertEqual(self.strategy.symbol, "NIFTY")
        self.assertEqual(self.strategy.quantity, 10)
        self.assertEqual(self.strategy.bars_in_trade, 0)
        self.assertEqual(self.strategy.trailing_stop, 0.0)

    def test_mandatory_constants(self):
        """Verify mandatory risk parameters are present."""
        self.assertTrue(hasattr(strategy_template, 'ATR_SL_MULTIPLIER'))
        self.assertTrue(hasattr(strategy_template, 'ATR_TP_MULTIPLIER'))
        self.assertTrue(hasattr(strategy_template, 'BREAKEVEN_TRIGGER_R'))
        self.assertTrue(hasattr(strategy_template, 'TIME_STOP_BARS'))
        self.assertTrue(hasattr(strategy_template, 'MAX_RISK_PCT'))
        self.assertTrue(hasattr(strategy_template, 'MAX_DAILY_LOSS_PCT'))
        self.assertTrue(hasattr(strategy_template, 'CAPITAL'))

    def test_generate_signal_structure(self):
        """Test generate_signal function signature and return type."""
        # Create dummy dataframe
        dates = pd.date_range(start='2023-01-01', periods=60, freq='5min')
        df = pd.DataFrame({
            'open': np.random.randn(60) + 100,
            'high': np.random.randn(60) + 105,
            'low': np.random.randn(60) + 95,
            'close': np.random.randn(60) + 100,
            'volume': np.random.randint(100, 1000, 60)
        }, index=dates)

        action, score, details = strategy_template.generate_signal(df)

        self.assertIn(action, ['BUY', 'SELL', 'HOLD'])
        self.assertIsInstance(score, float)
        self.assertIsInstance(details, dict)

        # Check mandatory details
        self.assertIn('atr', details)
        self.assertIn('quantity', details)
        self.assertIn('sl', details)
        self.assertIn('tp', details)

    def test_cycle_no_data(self):
        """Test cycle handles empty data gracefully."""
        self.strategy.fetch_history = MagicMock(return_value=pd.DataFrame())
        try:
            self.strategy.cycle()
        except Exception as e:
            self.fail(f"cycle() raised Exception with empty data: {e}")

if __name__ == '__main__':
    unittest.main()
