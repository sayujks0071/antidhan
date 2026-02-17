
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to sys.path to allow imports
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

# Mock dependencies before importing service
sys.modules['database.apilog_db'] = MagicMock()
sys.modules['database.analyzer_db'] = MagicMock()
sys.modules['database.auth_db'] = MagicMock()
sys.modules['database.token_db'] = MagicMock() # Mocked later anyway but safe
settings_db_mock = MagicMock()
settings_db_mock.get_analyze_mode.return_value = False
sys.modules['database.settings_db'] = settings_db_mock
sys.modules['extensions'] = MagicMock()
sys.modules['services.telegram_alert_service'] = MagicMock()
sys.modules['utils.api_analyzer'] = MagicMock()
sys.modules['utils.logging'] = MagicMock()

# Now import service
from services.place_smart_order_service import place_smart_order

class TestPlaceSmartOrderRobustness(unittest.TestCase):
    def setUp(self):
        self.order_data = {
            "symbol": "INFY",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": "1",
            "pricetype": "MARKET",
            "product_type": "MIS",
            "strategy": "TEST_STRATEGY",
            "position_size": "0"
        }
        self.api_key = "test_api_key"
        self.auth_token = "test_auth_token"
        self.broker = "dhan_sandbox"

    @patch("services.place_smart_order_service.get_token")
    @patch("services.place_smart_order_service.import_broker_module")
    def test_security_id_required_before_broker(self, mock_import_broker, mock_get_token):
        """Test that SecurityId Required error is caught before sending to broker"""
        # Mock get_token to return None (token not found)
        mock_get_token.return_value = None

        success, response, status_code = place_smart_order(
            order_data=self.order_data,
            api_key=self.api_key,
            auth_token=self.auth_token,
            broker=self.broker
        )

        # Should fail with 400
        self.assertFalse(success)
        self.assertEqual(status_code, 400) # Assuming the service maps it to 400
        self.assertIn("SecurityId Required", response["message"])

        # Broker module should NOT be imported or used
        mock_import_broker.assert_not_called()

    @patch("services.place_smart_order_service.get_token")
    @patch("services.place_smart_order_service.import_broker_module")
    def test_invalid_token_check(self, mock_import_broker, mock_get_token):
        """Test that Invalid Token (missing auth) is caught"""
        mock_get_token.return_value = "12345"

        # Add apikey to order_data so validation passes
        order_data_with_key = self.order_data.copy()
        order_data_with_key["apikey"] = "dummy_key"

        # Call with None auth_token (simulating missing token)
        success, response, status_code = place_smart_order(
            order_data=order_data_with_key,
            api_key=None,
            auth_token=None,
            broker=self.broker
        )

        self.assertFalse(success)
        # Service returns 401 for missing token
        self.assertEqual(status_code, 401)
        self.assertIn("Invalid Token", response["message"])

        mock_import_broker.assert_not_called()

    @patch("services.place_smart_order_service.get_token")
    @patch("services.place_smart_order_service.import_broker_module")
    def test_retry_delegation(self, mock_import_broker, mock_get_token):
        """Test that retries are delegated to underlying client (service calls once)"""
        mock_get_token.return_value = "12345"

        # Mock broker module
        mock_broker = MagicMock()
        mock_import_broker.return_value = mock_broker

        # Mock place_smartorder_api to return 500 error
        # It returns (res, response_data, order_id)
        mock_res = MagicMock()
        mock_res.status = 500
        mock_broker.place_smartorder_api.return_value = (mock_res, {"status": "error"}, None)

        success, response, status_code = place_smart_order(
            order_data=self.order_data,
            api_key=self.api_key,
            auth_token=self.auth_token,
            broker=self.broker,
            smart_order_delay="0"
        )

        # Should call ONCE. The service layer no longer retries manually.
        # Retries happen inside place_smartorder_api via httpx_client.
        self.assertEqual(mock_broker.place_smartorder_api.call_count, 1)

        self.assertFalse(success)
        self.assertEqual(status_code, 500)

if __name__ == "__main__":
    unittest.main()
