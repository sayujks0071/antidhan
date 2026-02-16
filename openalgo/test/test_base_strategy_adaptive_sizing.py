import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add path
sys.path.append(os.getcwd())

# Ensure imports work even if files are not perfectly structured for test runner
try:
    from openalgo.strategies.utils.base_strategy import BaseStrategy
except ImportError:
    sys.path.append(os.path.join(os.getcwd(), 'openalgo'))
    from openalgo.strategies.utils.base_strategy import BaseStrategy

class TestBaseStrategyAdaptiveSizing(unittest.TestCase):
    def setUp(self):
        # Mock client and PM
        self.mock_client = MagicMock()
        self.mock_pm = MagicMock()

        # Patch PositionManager to return our mock
        self.pm_patcher = patch('openalgo.strategies.utils.base_strategy.PositionManager', return_value=self.mock_pm)
        self.MockPositionManager = self.pm_patcher.start()

        # Patch SmartOrder
        self.so_patcher = patch('openalgo.strategies.utils.base_strategy.SmartOrder')
        self.MockSmartOrder = self.so_patcher.start()

        # Instantiate strategy
        # Mock API key to avoid DB calls
        with patch.dict(os.environ, {'OPENALGO_APIKEY': 'test_key'}):
            self.strategy = BaseStrategy(symbol='NIFTY', client=self.mock_client)

        # Ensure PM is set (BaseStrategy sets it if PositionManager class exists)
        self.strategy.pm = self.mock_pm
        self.strategy.smart_order = self.MockSmartOrder.return_value

    def tearDown(self):
        self.pm_patcher.stop()
        self.so_patcher.stop()

    def test_execute_trade_defaults_to_adaptive(self):
        # Setup
        self.mock_client.get_quote.return_value = {'ltp': 100}
        self.mock_pm.calculate_adaptive_quantity_monthly_atr.return_value = 50

        # Mock get_monthly_atr on the strategy instance (since it calls API)
        self.strategy.get_monthly_atr = MagicMock(return_value=10.0)

        # Act: Call execute_trade with quantity=None
        self.strategy.execute_trade("BUY", quantity=None)

        # Assert
        # 1. get_monthly_atr called?
        self.strategy.get_monthly_atr.assert_called()

        # 2. PM calculated adaptive qty?
        self.mock_pm.calculate_adaptive_quantity_monthly_atr.assert_called()

        # 3. SmartOrder placed order with calculated qty (50)?
        self.strategy.smart_order.place_adaptive_order.assert_called_with(
            strategy=self.strategy.name,
            symbol='NIFTY',
            action='BUY',
            exchange='NSE',
            quantity=50, # Expect 50 from mock
            limit_price=None,
            product='MIS',
            urgency='MEDIUM'
        )

if __name__ == '__main__':
    unittest.main()
