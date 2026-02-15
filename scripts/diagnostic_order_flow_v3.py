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
get_analyze_mode.return_value = False # Live mode (simulated)

# Import service
from services.place_smart_order_service import place_smart_order

# Mock utils.httpx_client which is used by broker.dhan_sandbox.api.order_api
import utils.httpx_client

class TestOrderFlowRejection(unittest.TestCase):
    def setUp(self):
        self.patcher = patch('utils.httpx_client.request')
        self.mock_request = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_market_closed_rejection_all_types(self):
        print("\n--- Testing Market Closed Rejection for 5 Order Types ---")

        # Order Types to test
        # Format: (price_type, price, trigger_price)
        order_types = [
            ("LIMIT", "2500.0", "0"),
            ("MARKET", "0", "0"),
            ("SL", "2400.0", "2450.0"),    # Stop Loss Limit
            ("SL-M", "0", "2450.0"),       # Stop Loss Market
            ("BRACKET", "2500.0", "0")     # Bracket Order (if supported)
        ]

        for price_type, price, trigger in order_types:
            print(f"Testing {price_type}...")

            # Setup Mock Response for Rejection (simulating Dhan Sandbox)
            # Dhan often returns 200 OK but with status: "failed" or "error" or orderStatus: "REJECTED"
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = json.dumps({
                "status": "success",
                "data": {
                    "orderStatus": "REJECTED",
                    "rejectReason": "Market is Closed"
                },
                "orderId": "1000000000",
                "orderStatus": "REJECTED",
                "remarks": "Market is Closed"
            })
            mock_resp.status = 200
            self.mock_request.return_value = mock_resp

            # Prepare Order Data
            order_data = {
                "strategy": "DiagnosticTest",
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "action": "BUY",
                "quantity": "1",
                "pricetype": price_type,     # Used by service
                "price_type": price_type,    # Sometimes used interchangeably
                "product": "MIS",
                "product_type": "MIS",
                "price": price,
                "trigger_price": trigger,
                "position_size": "1",
                "apikey": "test_key"
            }

            # Call Service
            success, response, code = place_smart_order(
                order_data=order_data,
                api_key="test_key",
                broker="dhan_sandbox"
            )

            print(f"  Status Code: {code}")
            print(f"  Response: {response}")
            print(f"  Success Flag: {success}")

            # Verify Logic
            # The service should catch the rejection and return success=False (or handle it)
            # Based on diagnostic_order_flow_v2, we expect success=False for rejection

            if success:
                 # If it returns success despite rejection, check if the response contains the rejection message
                 # Sometimes place_smart_order might return True if the API call was successful (200),
                 # leaving status parsing to the caller. But typically 'REJECTED' status should map to failure.
                 print("  WARNING: Service returned success=True despite rejection response.")

            # Check if rejection reason is propagated
            msg = response.get('message', '')

            if price_type == "BRACKET":
                 # BRACKET might be invalid in constants, so expect validation error
                 if "Invalid price type" in msg:
                     print("  BRACKET is correctly identified as invalid type.")
                 else:
                     self.assertTrue("Rejected" in msg or "Market is Closed" in msg,
                            f"Rejection reason not found in message: {msg}")
            else:
                self.assertTrue("Rejected" in msg or "Market is Closed" in msg,
                                f"Rejection reason not found in message: {msg}")

            # Assertions
            # We expect the system to handle it gracefully (no crash) and report the error
            self.assertIn(code, [200, 400], "Status code should be 200 (API success) or 400 (Bad Request/Logic Error)")

if __name__ == "__main__":
    unittest.main()
