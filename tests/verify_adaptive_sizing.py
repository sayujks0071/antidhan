import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import logging

# Add project root to path
sys.path.insert(0, os.path.abspath(os.getcwd()))

# Mock dependencies
sys.modules['database.auth_db'] = MagicMock()
sys.modules['utils.httpx_client'] = MagicMock()

# Now import BaseStrategy
from openalgo.strategies.utils.base_strategy import BaseStrategy

class TestAdaptiveSizing(unittest.TestCase):
    def setUp(self):
        # Create a mock dataframe
        self.df = pd.DataFrame({
            'timestamp': pd.date_range(start='2023-01-01', periods=100, freq='5min'),
            'open': [100.0] * 100,
            'high': [105.0] * 100,
            'low': [95.0] * 100,
            'close': [100.0] * 100,
            'volume': [1000] * 100
        })
        self.df['datetime'] = self.df['timestamp']

    @patch('openalgo.strategies.utils.base_strategy.APIClient')
    @patch('openalgo.strategies.utils.base_strategy.PositionManager')
    def test_adaptive_sizing_default(self, MockPM, MockClient):
        # Setup Strategy
        class MockStrategy(BaseStrategy):
            def get_signal(self, df):
                return "BUY", 1

        strategy = MockStrategy(symbol="TEST", quantity=1, capital=500000, risk=1.0)

        # Mock Client History
        strategy.client.history = MagicMock(return_value=self.df)

        # Mock PositionManager
        pm_instance = MockPM.return_value
        pm_instance.position = 0
        pm_instance.has_position.return_value = False
        strategy.pm = pm_instance

        # Mock ATR data (via pm or direct)
        # get_adaptive_quantity calls self.get_monthly_atr() which calls self.pm.get_monthly_atr()
        pm_instance.get_monthly_atr.return_value = 10.0

        # Mock calculation result
        # expected_qty = (500000 * 0.01) / (10 * 2) = 250
        pm_instance.calculate_adaptive_quantity_monthly_atr.return_value = 250

        # Mock buy method to capture arguments
        strategy.buy = MagicMock()

        # Run cycle
        strategy.default_cycle()

        # Assertions
        # 1. Verify fetch_history was called
        self.assertTrue(strategy.client.history.called)

        # 2. Verify adaptive calculation was requested
        pm_instance.get_monthly_atr.assert_called()
        pm_instance.calculate_adaptive_quantity_monthly_atr.assert_called_with(500000, 1.0, 10.0, 100.0)

        # 3. Verify buy was called with adaptive quantity (250)
        strategy.buy.assert_called_with(250, 100.0)
        print("Verified: Adaptive Quantity 250 was used instead of Default 1")

    @patch('openalgo.strategies.utils.base_strategy.APIClient')
    @patch('openalgo.strategies.utils.base_strategy.PositionManager')
    def test_adaptive_sizing_override(self, MockPM, MockClient):
        # Setup Strategy with explicit override
        class OverrideStrategy(BaseStrategy):
            def get_signal(self, df):
                return "BUY", 50 # Explicitly return 50

        strategy = OverrideStrategy(symbol="TEST", quantity=1, capital=500000, risk=1.0)

        # Mock Client History
        strategy.client.history = MagicMock(return_value=self.df)

        # Mock PositionManager
        pm_instance = MockPM.return_value
        pm_instance.position = 0
        pm_instance.has_position.return_value = False
        strategy.pm = pm_instance
        pm_instance.get_monthly_atr.return_value = 10.0
        pm_instance.calculate_adaptive_quantity_monthly_atr.return_value = 250

        # Mock buy method
        strategy.buy = MagicMock()

        # Run cycle
        strategy.default_cycle()

        # Assertions
        # 1. Verify adaptive calc was called (it happens before signal)
        pm_instance.calculate_adaptive_quantity_monthly_atr.assert_called()

        # 2. Verify buy was called with signal quantity (50) NOT adaptive (250)
        strategy.buy.assert_called_with(50, 100.0)
        print("Verified: Signal Quantity 50 overrode Adaptive Quantity 250")

if __name__ == '__main__':
    logging.basicConfig(level=logging.CRITICAL)
    unittest.main()
