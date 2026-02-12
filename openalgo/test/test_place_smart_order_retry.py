import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add openalgo directory to sys.path to allow imports
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

# Mock modules that might not be available or need mocking
sys.modules['utils.logging'] = MagicMock()
sys.modules['database.apilog_db'] = MagicMock()
sys.modules['database.analyzer_db'] = MagicMock()
sys.modules['database.auth_db'] = MagicMock()
sys.modules['database.token_db'] = MagicMock()
sys.modules['database.settings_db'] = MagicMock()
sys.modules['extensions'] = MagicMock()
sys.modules['extensions.socketio'] = MagicMock()
sys.modules['services.telegram_alert_service'] = MagicMock()
sys.modules['services.sandbox_service'] = MagicMock()
sys.modules['utils.api_analyzer'] = MagicMock()

# Now import the service to test
from services.place_smart_order_service import place_smart_order, place_smart_order_with_auth

class TestPlaceSmartOrderService(unittest.TestCase):

    def setUp(self):
        # Disable analyze mode to test live broker interaction
        sys.modules['database.settings_db'].get_analyze_mode.return_value = False

        self.order_data = {
            "apikey": "test_api_key",
            "strategy": "test_strategy",
            "symbol": "TESTSYMBOL",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": "10",
            "position_size": "0",
            "product_type": "MIS",
            "price_type": "MARKET"
        }
        self.auth_token = "valid_token"
        self.broker = "dhan_sandbox"

    @patch('services.place_smart_order_service.get_token')
    def test_security_id_required(self, mock_get_token):
        """Test that missing SecurityId returns 400 error before broker call"""
        # Mock get_token to return None (SecurityId not found)
        mock_get_token.return_value = None

        # We also need to mock import_broker_module to ensure it's not called if validation fails
        with patch('services.place_smart_order_service.import_broker_module') as mock_import:
            success, response, status_code = place_smart_order_with_auth(
                self.order_data, self.auth_token, self.broker, self.order_data
            )

            self.assertFalse(success)
            self.assertEqual(status_code, 400)
            self.assertEqual(response['message'], "SecurityId Required")

            # Broker module should NOT be imported/called
            mock_import.assert_not_called()

    @patch('services.place_smart_order_service.get_token')
    def test_invalid_token(self, mock_get_token):
        """Test that missing auth_token returns 401 error before broker call"""
        # Mock get_token to return a valid token
        mock_get_token.return_value = "12345"

        # Pass None as auth_token
        invalid_token = None

        with patch('services.place_smart_order_service.import_broker_module') as mock_import:
            success, response, status_code = place_smart_order_with_auth(
                self.order_data, invalid_token, self.broker, self.order_data
            )

            self.assertFalse(success)
            self.assertEqual(status_code, 401)
            self.assertEqual(response['message'], "Invalid Token: Authentication token is missing or empty")

            # Broker module should NOT be imported/called
            mock_import.assert_not_called()

    @patch('services.place_smart_order_service.get_token')
    @patch('services.place_smart_order_service.import_broker_module')
    def test_retry_mechanism_success_after_failure(self, mock_import, mock_get_token):
        """Test that 500 error triggers retry and eventually succeeds"""
        mock_get_token.return_value = "12345"

        # Mock broker module
        mock_broker = MagicMock()
        mock_import.return_value = mock_broker

        # Mock place_smartorder_api responses:
        # 1. 500 Error
        # 2. 503 Error
        # 3. Success (200)

        response_500 = MagicMock()
        response_500.status = 500
        response_500.status_code = 500

        response_503 = MagicMock()
        response_503.status = 503
        response_503.status_code = 503

        response_200 = MagicMock()
        response_200.status = 200
        response_200.status_code = 200

        # Side effect for place_smartorder_api
        mock_broker.place_smartorder_api.side_effect = [
            (response_500, {"message": "Internal Server Error"}, None),
            (response_503, {"message": "Service Unavailable"}, None),
            (response_200, {"message": "Order Placed", "orderId": "1001"}, "1001")
        ]

        success, response, status_code = place_smart_order_with_auth(
            self.order_data, self.auth_token, self.broker, self.order_data, smart_order_delay="0"
        )

        self.assertTrue(success)
        self.assertEqual(status_code, 200)
        self.assertEqual(response.get("orderid"), "1001")

        # Verify it was called 3 times (2 retries + 1 success)
        self.assertEqual(mock_broker.place_smartorder_api.call_count, 3)

    @patch('services.place_smart_order_service.get_token')
    @patch('services.place_smart_order_service.import_broker_module')
    def test_retry_mechanism_fails_after_retries(self, mock_import, mock_get_token):
        """Test that 500 error triggers retry and fails after max retries"""
        mock_get_token.return_value = "12345"

        mock_broker = MagicMock()
        mock_import.return_value = mock_broker

        response_500 = MagicMock()
        response_500.status = 500
        response_500.status_code = 500

        # Fail 4 times (Initial + 3 retries)
        mock_broker.place_smartorder_api.return_value = (response_500, {"message": "Error"}, None)

        success, response, status_code = place_smart_order_with_auth(
            self.order_data, self.auth_token, self.broker, self.order_data, smart_order_delay="0"
        )

        self.assertFalse(success)
        # Should return the last error status
        self.assertEqual(status_code, 500)

        # Verify call count: 1 initial + 3 retries = 4 calls
        self.assertEqual(mock_broker.place_smartorder_api.call_count, 4)

if __name__ == '__main__':
    unittest.main()
