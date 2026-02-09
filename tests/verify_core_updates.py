import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime

# Add path
sys.path.append(os.path.join(os.getcwd(), 'openalgo/strategies/utils'))
# Also add root
sys.path.append(os.getcwd())

# Mock openalgo_observability
sys.modules['openalgo_observability'] = MagicMock()
sys.modules['openalgo_observability.logging_setup'] = MagicMock()

try:
    from trading_utils import APIClient, PositionManager
except ImportError:
    # Try importing directly if path is weird
    sys.path.append('openalgo/strategies/utils')
    from trading_utils import APIClient, PositionManager

class TestCoreUpdates(unittest.TestCase):

    def test_position_manager_sizing(self):
        pm = PositionManager("TEST")

        # Test 1: Basic Sizing
        # Capital 100k, Risk 1%, ATR 10, Price 1000
        # Risk Amount = 1000
        # Stop Distance = 20 (2*ATR)
        # Qty = 1000 / 20 = 50
        qty = pm.calculate_adaptive_quantity(100000, 1.0, 10.0, 1000.0)
        self.assertEqual(qty, 50)

        # Test 2: Capital Limit
        # Capital 10000, Price 1000 -> Max Qty 10
        # Risk Amount = 100 (1%)
        # Stop Dist = 2 (ATR=1)
        # Qty = 50 (Calculation)
        # But Max is 10
        qty = pm.calculate_adaptive_quantity(10000, 1.0, 1.0, 1000.0)
        self.assertEqual(qty, 10)

        # Test 3: Monthly ATR Sizing
        # Same params but different method
        qty_monthly = pm.calculate_adaptive_quantity_monthly_atr(100000, 1.0, 10.0, 1000.0)
        self.assertEqual(qty_monthly, 50)

        print("PositionManager Sizing: OK")

    @patch('trading_utils.httpx_client.post')
    def test_api_client_caching(self, mock_post):
        client = APIClient(api_key="test")

        # Mock Response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "success",
            "data": [{"timestamp": 1600000000, "close": 100}]
        }
        mock_post.return_value = mock_resp

        # First Call
        df1 = client.history("TEST", "NSE", "5m")
        self.assertFalse(df1.empty)
        self.assertEqual(mock_post.call_count, 1)

        # Second Call (Should hit LRU cache)
        df2 = client.history("TEST", "NSE", "5m")
        self.assertFalse(df2.empty)
        # Call count should still be 1 because of lru_cache
        self.assertEqual(mock_post.call_count, 1)

        # Third Call with diff args
        df3 = client.history("TEST2", "NSE", "5m")
        self.assertEqual(mock_post.call_count, 2)

        print("APIClient Caching: OK")

if __name__ == '__main__':
    unittest.main()
