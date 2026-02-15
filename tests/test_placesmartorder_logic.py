
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add openalgo to sys.path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

# Set dummy env vars BEFORE importing modules that use them
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['API_RATE_LIMIT'] = '100 per minute'
os.environ['API_KEY_PEPPER'] = 'dummy_pepper_for_testing_must_be_at_least_32_chars_long'

# Mock database.telegram_db before import to prevent SQL error
sys.modules['database.telegram_db'] = MagicMock()

# Now import
try:
    from services.place_smart_order_service import place_smart_order
except ImportError:
    # If import fails, we might need to mock some DB modules if they try to connect on import
    # But for now let's see if setting DATABASE_URL is enough
    raise

class TestPlaceSmartOrder(unittest.TestCase):
    @patch('services.place_smart_order_service.get_analyze_mode')
    @patch('services.place_smart_order_service.get_token')
    @patch('services.place_smart_order_service.executor')
    @patch('services.place_smart_order_service.import_broker_module')
    @patch('services.place_smart_order_service.async_log_order')
    @patch('services.place_smart_order_service.socketio')
    @patch('services.place_smart_order_service.telegram_alert_service')
    def test_security_id_required(self, mock_telegram, mock_socket, mock_log, mock_import, mock_executor, mock_get_token, mock_analyze):
        # Setup
        mock_analyze.return_value = False # Live mode
        mock_get_token.return_value = None # Token not found (Invalid Symbol)

        order_data = {
            "apikey": "dummy_key",
            "strategy": "test_strategy",
            "symbol": "INVALID_SYMBOL",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": "1",
            "position_size": "0",
            "product": "MIS",
            "pricetype": "MARKET"
        }

        # Execute
        success, response, status = place_smart_order(
            order_data=order_data,
            auth_token="valid_token",
            broker="dhan_sandbox"
        )

        # Verify
        self.assertFalse(success)
        self.assertEqual(response['message'], "SecurityId Required")
        # Ensure broker module was NOT imported/called
        mock_import.assert_not_called()

    @patch('services.place_smart_order_service.get_analyze_mode')
    @patch('services.place_smart_order_service.get_token')
    @patch('services.place_smart_order_service.executor')
    @patch('services.place_smart_order_service.import_broker_module')
    @patch('services.place_smart_order_service.async_log_order')
    @patch('services.place_smart_order_service.socketio')
    @patch('services.place_smart_order_service.telegram_alert_service')
    def test_invalid_token_missing(self, mock_telegram, mock_socket, mock_log, mock_import, mock_executor, mock_get_token, mock_analyze):
        # Setup
        mock_analyze.return_value = False
        mock_get_token.return_value = "12345" # Valid token

        order_data = {
            "apikey": "dummy_key",
            "strategy": "test_strategy",
            "symbol": "VALID_SYMBOL",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": "1",
            "position_size": "0",
            "product": "MIS",
            "pricetype": "MARKET"
        }

        # Execute with missing auth_token
        success, response, status = place_smart_order(
            order_data=order_data,
            auth_token=None,
            broker="dhan_sandbox"
        )

        # Verify
        self.assertFalse(success)
        self.assertIn("Invalid Token", response['message'])
        self.assertEqual(status, 401)
        mock_import.assert_not_called()

    @patch('services.place_smart_order_service.get_analyze_mode')
    @patch('services.place_smart_order_service.get_token')
    @patch('services.place_smart_order_service.executor')
    @patch('services.place_smart_order_service.import_broker_module')
    @patch('services.place_smart_order_service.async_log_order')
    @patch('services.place_smart_order_service.socketio')
    @patch('services.place_smart_order_service.telegram_alert_service')
    def test_retry_mechanism(self, mock_telegram, mock_socket, mock_log, mock_import, mock_executor, mock_get_token, mock_analyze):
        # Setup
        mock_analyze.return_value = False
        mock_get_token.return_value = "12345"

        mock_broker = MagicMock()
        mock_import.return_value = mock_broker

        # Mock broker response to simulate 500 error then success
        # attempt 1: 500
        # attempt 2: 200

        mock_res_500 = MagicMock()
        mock_res_500.status = 500

        mock_res_200 = MagicMock()
        mock_res_200.status = 200

        mock_broker.place_smartorder_api.side_effect = [
            (mock_res_500, {"status": "error"}, None),
            (mock_res_200, {"status": "success"}, "ORDER123")
        ]

        order_data = {
            "apikey": "dummy_key",
            "strategy": "test_strategy",
            "symbol": "VALID_SYMBOL",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": "1",
            "position_size": "0",
            "product": "MIS",
            "pricetype": "MARKET"
        }

        # Execute
        # Set delay to 0 to speed up test
        success, response, status = place_smart_order(
            order_data=order_data,
            auth_token="valid_token",
            broker="dhan_sandbox",
            smart_order_delay="0"
        )

        # Verify
        self.assertTrue(success)
        self.assertEqual(response.get('orderid'), "ORDER123")
        # Check that place_smartorder_api was called twice
        self.assertEqual(mock_broker.place_smartorder_api.call_count, 2)

if __name__ == '__main__':
    unittest.main()
