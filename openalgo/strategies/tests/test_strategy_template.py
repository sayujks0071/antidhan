import sys
import os
import unittest
import pandas as pd
from unittest.mock import MagicMock

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

# Mock environment variables
os.environ['OPENALGO_APIKEY'] = 'test_key'

from openalgo.strategies.scripts.strategy_template import YourStrategy, generate_signal

class TestStrategyTemplate(unittest.TestCase):
    def setUp(self):
        self.strategy = YourStrategy(symbol="SBIN", quantity=10, api_key="test", host="http://localhost")
        # Disable logging for tests
        self.strategy.logger = MagicMock()

    def test_instantiation(self):
        self.assertIsNotNone(self.strategy)
        self.assertEqual(self.strategy.symbol, "SBIN")
        self.assertEqual(self.strategy.quantity, 10)

    def test_generate_signal(self):
        # Create dummy dataframe
        data = {
            'open': [100, 101, 102] * 20,
            'high': [105, 106, 107] * 20,
            'low': [95, 96, 97] * 20,
            'close': [102, 103, 104] * 20,
            'volume': [1000, 1100, 1200] * 20
        }
        df = pd.DataFrame(data)

        action, score, details = generate_signal(df, symbol="SBIN")

        self.assertIn(action, ['BUY', 'SELL', 'HOLD'])
        self.assertIsInstance(score, float)
        self.assertIsInstance(details, dict)
        self.assertIn('atr', details)
        self.assertIn('quantity', details)

if __name__ == '__main__':
    unittest.main()
