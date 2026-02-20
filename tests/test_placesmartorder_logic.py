import sys
import unittest
import os
from unittest.mock import MagicMock, patch

# Add repo root to path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Mock dependencies BEFORE import
sys.modules['database'] = MagicMock()
sys.modules['database.analyzer_db'] = MagicMock()
sys.modules['database.apilog_db'] = MagicMock()
sys.modules['database.auth_db'] = MagicMock()
sys.modules['database.settings_db'] = MagicMock()
sys.modules['database.token_db'] = MagicMock()
sys.modules['extensions'] = MagicMock()
sys.modules['services'] = MagicMock()
sys.modules['services.telegram_alert_service'] = MagicMock()
sys.modules['services.sandbox_service'] = MagicMock()
sys.modules['utils'] = MagicMock()
sys.modules['utils.api_analyzer'] = MagicMock()
sys.modules['utils.logging'] = MagicMock()
sys.modules['utils.constants'] = MagicMock()

# Set up constants mock
constants_mock = sys.modules['utils.constants']
constants_mock.REQUIRED_SMART_ORDER_FIELDS = ['symbol', 'exchange', 'action', 'quantity']
constants_mock.VALID_EXCHANGES = ['NSE', 'BSE', 'MCX']
constants_mock.VALID_ACTIONS = ['BUY', 'SELL']
constants_mock.VALID_PRICE_TYPES = ['MARKET', 'LIMIT', 'SL', 'SL-M']
constants_mock.VALID_PRODUCT_TYPES = ['CNC', 'NRML', 'MIS', 'BO', 'CO']

# Import target module
from openalgo.services.place_smart_order_service import place_smart_order_with_auth

class TestPlaceSmartOrderLogic(unittest.TestCase):
    def setUp(self):
        # Reset mocks
        sys.modules['database.settings_db'].get_analyze_mode.return_value = False
        sys.modules['database.token_db'].get_token.return_value = "12345"

    @patch('openalgo.services.place_smart_order_service.import_broker_module')
    def test_place_smart_order_success(self, mock_import):
        # Mock broker module
        mock_broker = MagicMock()
        mock_import.return_value = mock_broker

        # Mock API response: Success, Order Placed
        res = MagicMock()
        res.status = 200
        response_data = {"status": "success", "orderId": "ORD123"}
        order_id = "ORD123"
        mock_broker.place_smartorder_api.return_value = (res, response_data, order_id)

        order_data = {
            "symbol": "RELIANCE", "exchange": "NSE", "action": "BUY", "quantity": "1",
            "price_type": "MARKET", "product_type": "MIS"
        }
        original_data = order_data.copy()

        # Call function
        success, response, status = place_smart_order_with_auth(
            order_data, "auth_token", "dhan", original_data, smart_order_delay="0"
        )

        # Verify
        self.assertTrue(success)
        self.assertEqual(status, 200)
        self.assertEqual(response['orderid'], "ORD123")

    @patch('openalgo.services.place_smart_order_service.import_broker_module')
    def test_place_smart_order_business_failure(self, mock_import):
        # Mock broker module
        mock_broker = MagicMock()
        mock_import.return_value = mock_broker

        # Mock API response: HTTP 200 but Order Rejected (order_id None)
        res = MagicMock()
        res.status = 200
        response_data = {"status": "error", "message": "Invalid Token provided"}
        order_id = None
        mock_broker.place_smartorder_api.return_value = (res, response_data, order_id)

        order_data = {
            "symbol": "RELIANCE", "exchange": "NSE", "action": "BUY", "quantity": "1"
        }
        original_data = order_data.copy()

        # Call function
        success, response, status = place_smart_order_with_auth(
            order_data, "auth_token", "dhan", original_data, smart_order_delay="0"
        )

        # Verify: Should be False, with correct status code logic
        self.assertFalse(success)
        # "Invalid Token" -> 401 per logic
        self.assertEqual(status, 401)
        self.assertIn("Invalid Token", response['message'])

if __name__ == '__main__':
    unittest.main()
