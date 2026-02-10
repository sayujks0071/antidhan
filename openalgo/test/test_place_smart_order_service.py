
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add openalgo to sys.path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

# Mock dependencies
sys.modules['database.analyzer_db'] = MagicMock()
sys.modules['database.apilog_db'] = MagicMock()
sys.modules['database.auth_db'] = MagicMock()
sys.modules['database.settings_db'] = MagicMock()
sys.modules['database.token_db'] = MagicMock()
sys.modules['extensions'] = MagicMock()
sys.modules['services.telegram_alert_service'] = MagicMock()
sys.modules['utils.api_analyzer'] = MagicMock()
sys.modules['utils.logging'] = MagicMock()
sys.modules['pytz'] = MagicMock()
sys.modules['sqlalchemy'] = MagicMock()
sys.modules['flask'] = MagicMock()
sys.modules['flask_socketio'] = MagicMock()

# Mock order_router_service to avoid deeper imports
mock_order_router = MagicMock()
mock_order_router.should_route_to_pending.return_value = False
sys.modules['services.order_router_service'] = mock_order_router

# Mock get_analyze_mode to return False (Live mode)
sys.modules['database.settings_db'].get_analyze_mode.return_value = False

# Mock get_token to return a valid token
sys.modules['database.token_db'].get_token.return_value = "12345"

from services.place_smart_order_service import place_smart_order

class TestPlaceSmartOrderService(unittest.TestCase):

    @patch('services.place_smart_order_service.import_broker_module')
    @patch('services.place_smart_order_service.get_auth_token_broker')
    def test_invalid_token_from_broker(self, mock_get_auth, mock_import):
        # Setup
        mock_get_auth.return_value = ("valid_token_string", "dhan_sandbox")

        mock_broker = MagicMock()
        mock_import.return_value = mock_broker

        # Simulate Broker returning "Invalid Token" (res=None)
        # Dhan Sandbox behavior: return None, {"status": "error", "message": "Invalid Token"}, None
        mock_broker.place_smartorder_api.return_value = (None, {"status": "error", "message": "Invalid Token"}, None)

        order_data = {
            "strategy": "TEST_STRATEGY",
            "symbol": "SBIN",
            "exchange": "NSE",
            "action": "BUY",
            "product": "MIS",
            "quantity": "1",
            "price_type": "MARKET",
            "position_size": "0"
        }

        # Execute
        success, response, status_code = place_smart_order(order_data, api_key="test_key")

        # Verify
        print(f"Status Code: {status_code}")
        print(f"Response: {response}")

        # Desired behavior: Status Code should be 401
        self.assertEqual(status_code, 401, "Should be 401 for Invalid Token")
        self.assertEqual(response['message'], "Invalid Token")

    @patch('services.place_smart_order_service.import_broker_module')
    @patch('services.place_smart_order_service.get_auth_token_broker')
    def test_security_id_required_from_broker(self, mock_get_auth, mock_import):
        # Setup
        mock_get_auth.return_value = ("valid_token_string", "dhan_sandbox")

        mock_broker = MagicMock()
        mock_import.return_value = mock_broker

        # Simulate Broker returning "SecurityId Required" (res=None)
        mock_broker.place_smartorder_api.return_value = (None, {"status": "error", "message": "SecurityId Required"}, None)

        order_data = {
            "strategy": "TEST_STRATEGY",
            "symbol": "SBIN",
            "exchange": "NSE",
            "action": "BUY",
            "product": "MIS",
            "quantity": "1",
            "price_type": "MARKET",
            "position_size": "0"
        }

        # Execute
        success, response, status_code = place_smart_order(order_data, api_key="test_key")

        # Verify
        print(f"Status Code: {status_code}")
        print(f"Response: {response}")

        # Desired behavior: Status Code should be 400
        self.assertEqual(status_code, 400, "Should be 400 for SecurityId Required")
        self.assertEqual(response['message'], "SecurityId Required")

    @patch('services.place_smart_order_service.time.sleep')
    @patch('services.place_smart_order_service.import_broker_module')
    @patch('services.place_smart_order_service.get_auth_token_broker')
    def test_retry_on_connection_error(self, mock_get_auth, mock_import, mock_sleep):
        # Setup
        mock_get_auth.return_value = ("valid_token_string", "dhan_sandbox")
        mock_broker = MagicMock()
        mock_import.return_value = mock_broker

        # Simulate transient error then success
        # First call: ConnectionError (res=None)
        # Second call: Success
        mock_broker.place_smartorder_api.side_effect = [
            (None, {"errorType": "ConnectionError", "errorMessage": "Timeout"}, None),
            (MagicMock(status=200), {"status": "success", "message": "Order placed"}, "12345")
        ]

        order_data = {
            "strategy": "TEST_STRATEGY",
            "symbol": "SBIN",
            "exchange": "NSE",
            "action": "BUY",
            "product": "MIS",
            "quantity": "1",
            "price_type": "MARKET",
            "position_size": "0"
        }

        # Execute
        success, response, status_code = place_smart_order(order_data, api_key="test_key")

        # Verify
        print(f"Status Code: {status_code}")
        print(f"Response: {response}")

        self.assertEqual(status_code, 200, "Should succeed after retry")
        self.assertEqual(mock_broker.place_smartorder_api.call_count, 2, "Should have retried once")
        # mock_sleep.assert_called_once() # Called twice: once for retry, once for smart_order_delay
        self.assertGreaterEqual(mock_sleep.call_count, 1)

if __name__ == '__main__':
    unittest.main()
