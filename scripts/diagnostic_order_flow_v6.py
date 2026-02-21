import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add openalgo to path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

# Mock modules that might cause import errors or are not needed
sys.modules['database.analyzer_db'] = MagicMock()
sys.modules['database.apilog_db'] = MagicMock()
sys.modules['extensions'] = MagicMock()
sys.modules['utils.api_analyzer'] = MagicMock()
sys.modules['services.telegram_alert_service'] = MagicMock()

# Mock settings_db BEFORE importing service
mock_settings_db = MagicMock()
mock_settings_db.get_analyze_mode.return_value = False # Force Live Mode
sys.modules['database.settings_db'] = mock_settings_db

# Now import target
from services.place_smart_order_service import place_smart_order

class TestOrderFlow(unittest.TestCase):
    def setUp(self):
        self.mock_token_patcher = patch('services.place_smart_order_service.get_token')
        self.mock_token = self.mock_token_patcher.start()
        self.mock_token.return_value = "12345" # valid token

        self.mock_import_patcher = patch('services.place_smart_order_service.import_broker_module')
        self.mock_import = self.mock_import_patcher.start()

        # Mock broker module
        self.mock_broker = MagicMock()
        self.mock_import.return_value = self.mock_broker

        # Mock Response object
        self.mock_response = MagicMock()
        self.mock_response.status = 200 # HTTP 200

    def tearDown(self):
        self.mock_token_patcher.stop()
        self.mock_import_patcher.stop()

    def test_rejected_orders(self):
        # Simulate REJECTED response from broker (Dhan Sandbox style)
        # return res, response_data, order_id
        # Rejected means order_id is None
        self.mock_broker.place_smartorder_api.return_value = (
            self.mock_response,
            {"status": "failed", "orderStatus": "REJECTED", "message": "Market Closed"},
            None
        )

        # Test 5 different order types as requested
        # Limit, Market, SL, SL-M, Bracket
        order_types = [
            {"type": "LIMIT", "price": 100, "trigger_price": 0},
            {"type": "MARKET", "price": 0, "trigger_price": 0},
            {"type": "SL", "price": 100, "trigger_price": 99},
            {"type": "SL-M", "price": 0, "trigger_price": 99},
            {"type": "BO", "price": 100, "trigger_price": 99, "stop_loss": 5, "square_off": 10}
        ]

        for ot in order_types:
            print(f"\nTesting Order Type: {ot['type']}...")
            order_data = {
                "apikey": "dummy_key",
                "strategy": "TestStrategy",
                "position_size": "0",
                "symbol": "SBIN",
                "exchange": "NSE",
                "action": "BUY",
                "quantity": 1,
                "price_type": ot['type'],
                "product_type": "MIS",
                "price": ot.get("price", 0),
                "trigger_price": ot.get("trigger_price", 0)
            }
            if "stop_loss" in ot:
                order_data["stop_loss"] = ot["stop_loss"]
                order_data["square_off"] = ot["square_off"]

            # Use 'dhan_sandbox' broker
            success, response, status_code = place_smart_order(
                order_data,
                auth_token="test_token",
                broker="dhan_sandbox"
            )

            print(f"Result: success={success}, status={status_code}, response={response}")

            # Expect success=False, status=200 (as per service logic for business rejection), response contains error message
            self.assertFalse(success, f"Order {ot['type']} should be rejected")

            if ot['type'] == 'BO':
                # Bracket Order is currently not in VALID_PRICE_TYPES, so it should fail validation with 400
                self.assertEqual(status_code, 400, f"Order {ot['type']} should return status 400 (Invalid Type)")
                self.assertIn("Invalid price type", response.get("message", ""), f"Order {ot['type']} error message mismatch")
            else:
                self.assertEqual(status_code, 200, f"Order {ot['type']} should return status 200")
                self.assertIn("Market Closed", response.get("message", ""), f"Order {ot['type']} error message mismatch")

if __name__ == '__main__':
    unittest.main()
