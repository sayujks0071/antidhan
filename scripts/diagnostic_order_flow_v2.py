import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import json

# Set dummy env vars BEFORE importing modules that use them
os.environ['DATABASE_URL'] = "sqlite:///:memory:"
os.environ['APP_KEY'] = "test_key"
os.environ['BROKER_API_KEY'] = "test_broker_key"

# Add repo root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(current_dir)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
    sys.path.insert(0, os.path.join(repo_root, "openalgo"))

# Mock database modules before import
sys.modules['database.auth_db'] = MagicMock()
sys.modules['database.token_db'] = MagicMock()
sys.modules['database.settings_db'] = MagicMock()
sys.modules['database.analyzer_db'] = MagicMock()
sys.modules['database.apilog_db'] = MagicMock()
sys.modules['database.apilog_db'].executor = MagicMock() # Mock executor
sys.modules['extensions'] = MagicMock()
sys.modules['services.telegram_alert_service'] = MagicMock()

# Setup mocks for database functions
from database.auth_db import get_auth_token_broker
get_auth_token_broker.return_value = ("MOCK_TOKEN", "dhan_sandbox")

from database.token_db import get_token, get_br_symbol
get_token.return_value = "12345" # Mock Security ID
get_br_symbol.return_value = "RELIANCE"

from database.settings_db import get_analyze_mode
get_analyze_mode.return_value = False # Live mode

# Import service
from services.place_smart_order_service import place_smart_order

# Mock utils.httpx_client which is used by broker.dhan_sandbox.api.order_api
import utils.httpx_client

class TestOrderFlow(unittest.TestCase):
    def setUp(self):
        self.patcher = patch('utils.httpx_client.request')
        self.mock_request = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_order_types_flow(self):
        print("\n--- Testing 5 Order Types ---")
        order_types = [
            ("LIMIT", "100.0", "0"),
            ("MARKET", "0", "0"),
            ("SL", "100.0", "99.0"),
            ("SL-M", "0", "99.0"),
            ("BRACKET", "100.0", "0")
        ]

        for price_type, price, trigger in order_types:
            print(f"Testing {price_type}...")

            # Setup Mock Response for Success
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = json.dumps({
                "status": "success",
                "data": {"orderStatus": "PENDING"},
                "orderId": f"ORD_{price_type}"
            })
            mock_resp.status = 200

            self.mock_request.return_value = mock_resp

            order_data = {
                "strategy": "DiagnosticTest",
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "action": "BUY",
                "quantity": "1",
                "price_type": price_type,
                "product_type": "MIS",
                "price": price,
                "trigger_price": trigger,
                "position_size": "1", # Required field
                "apikey": "test_key",
                "pricetype": price_type,
                "product": "MIS"
            }

            success, response, code = place_smart_order(
                order_data=order_data,
                api_key="test_key"
            )

            if price_type == "BRACKET":
                # Assuming BRACKET is not valid in VALID_PRICE_TYPES if validation is strict
                # Check VALID_PRICE_TYPES in place_smart_order_service imports
                # But if validation passes, it goes to broker.
                if not success:
                    print(f"  Result: {price_type} Failed: {response['message']}")
                else:
                    print(f"  Result: {price_type} Success: {response}")
            else:
                if success:
                    print(f"  Result: {price_type} Success: {response}")
                else:
                    print(f"  Result: {price_type} Failed: {response['message']}")

    def test_market_closed_rejection(self):
        print("\n--- Testing Market Closed Rejection ---")
        # Setup Mock Response for Rejection (HTTP 200 but status REJECTED)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps({
            "status": "success",
            "orderStatus": "REJECTED",
            "orderId": "1000000000",
            "remarks": "Market is Closed"
        })
        mock_resp.status = 200
        self.mock_request.return_value = mock_resp

        order_data = {
            "strategy": "DiagnosticTest",
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": "1",
            "price_type": "MARKET",
            "pricetype": "MARKET",
            "product_type": "MIS",
            "product": "MIS",
            "price": "0",
            "trigger_price": "0",
            "position_size": "1",
            "apikey": "test_key"
        }

        success, response, code = place_smart_order(
            order_data=order_data,
            api_key="test_key"
        )

        print(f"  Status Code: {code}")
        print(f"  Response: {response}")
        print(f"  Success Flag: {success}")

        # Assertions
        self.assertFalse(success)
        self.assertEqual(code, 200)
        self.assertIn("Order Rejected", response['message'])
        self.assertIn("Market is Closed", response['message'])

if __name__ == "__main__":
    unittest.main()
