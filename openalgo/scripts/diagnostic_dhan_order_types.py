
import json
import logging
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Set dummy DATABASE_URL to avoid sqlalchemy error during import
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["BROKER_API_KEY"] = "mock_broker_key"

# Add repo root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
openalgo_root = os.path.dirname(script_dir)
if openalgo_root not in sys.path:
    sys.path.insert(0, openalgo_root)

# Mocking database modules to avoid connection errors during import
# Also mock services that are not focus of this test
sys.modules["database.analyzer_db"] = MagicMock()
sys.modules["database.apilog_db"] = MagicMock()
sys.modules["database.auth_db"] = MagicMock()
sys.modules["database.token_db"] = MagicMock()
sys.modules["database.symbol"] = MagicMock() # Mock symbol db
sys.modules["extensions"] = MagicMock()
sys.modules["services.telegram_alert_service"] = MagicMock()
sys.modules["services.sandbox_service"] = MagicMock()
sys.modules["pytz"] = MagicMock()
sys.modules["sqlalchemy"] = MagicMock()
sys.modules["h2"] = MagicMock()
sys.modules["structlog"] = MagicMock()
sys.modules["httpx"] = MagicMock()
sys.modules["cachetools"] = MagicMock()
sys.modules["openalgo_observability"] = MagicMock()
sys.modules["openalgo_observability.logging_setup"] = MagicMock()

# Configure settings_db mock
settings_db_mock = MagicMock()
settings_db_mock.get_analyze_mode.return_value = False
sys.modules["database.settings_db"] = settings_db_mock

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DiagnosticDhanOrderTypes")

# Ensure utils.httpx_client is loaded for patching
import utils.httpx_client

# Import the service under test
# Note: token_db.get_token is used in place_smart_order_service AND broker.dhan_sandbox.api.order_api
# We need to mock get_token to return something valid
with patch("database.token_db.get_token") as mock_get_token:
    mock_get_token.return_value = "12345" # Dummy Security ID
    from services.place_smart_order_service import place_smart_order

class TestDhanOrderTypes(unittest.TestCase):

    @patch("utils.httpx_client.request")
    def test_market_closed_rejection(self, mock_request):
        """
        Simulate placing 5 order types and receiving REJECTED status from Dhan Sandbox.
        """
        logger.info("Starting Diagnostic Order Flow Test...")

        def request_side_effect(method, url, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.status = 200

            if "positions" in url:
                # Mock get_positions response - Empty positions
                mock_resp.text = json.dumps([])
                return mock_resp

            if "orders" in url and method == "POST":
                # Mock place_order response - REJECTED
                resp_data = {
                    "status": "success",
                    "orderId": "10001",
                    "orderStatus": "REJECTED",
                    "remarks": "Market is Closed",
                    "data": {
                        "rejectReason": "Market Closed"
                    }
                }
                mock_resp.text = json.dumps(resp_data)
                return mock_resp

            # Default
            mock_resp.text = "{}"
            return mock_resp

        mock_request.side_effect = request_side_effect

        # Order Types to Test
        order_types = {
            "LIMIT": "LIMIT",
            "MARKET": "MARKET",
            "STOP_LOSS": "SL",
            "STOP_LOSS_MARKET": "SL-M",
            "BRACKET_ORDER": "BO"
        }

        success_count = 0
        failure_count = 0

        for name, price_type in order_types.items():
            logger.info(f"--- Testing Order Type: {name} ({price_type}) ---")

            order_data = {
                "apikey": "mock_api_key",
                "strategy": "Diagnostic",
                "symbol": "SBIN",
                "exchange": "NSE",
                "action": "BUY",
                "quantity": 1,
                "position_size": 1,
                "price_type": price_type, # Used for validation in service
                "pricetype": price_type,  # Used by Dhan API mapping
                "product_type": "MIS",
                "product": "MIS",
                "price": 100,
                "trigger_price": 90 if "SL" in price_type else 0
            }

            # Use auth_token and broker to hit the broker logic
            success, response, status_code = place_smart_order(
                order_data,
                auth_token="mock_token",
                broker="dhan_sandbox"
            )

            logger.info(f"Result for {name}: Success={success}, Status={status_code}, Msg={response.get('message')}")

            if name == "BRACKET_ORDER":
                # BO is not in VALID_PRICE_TYPES in place_smart_order_service (usually), check response
                if not success and status_code == 400 and "Invalid price type" in str(response.get("message", "")):
                     logger.info("PASS: BRACKET_ORDER correctly rejected by validation (Unsupported type).")
                     success_count += 1
                else:
                     logger.warning(f"FAIL: BRACKET_ORDER unexpected result: {response}")
                     failure_count += 1
                continue

            # For supported types, we expect failure due to "Market Closed" rejection mocked above
            if not success:
                if "Rejected" in str(response.get("message")) or "Market is Closed" in str(response.get("message")):
                    logger.info(f"PASS: {name} correctly rejected by broker.")
                    success_count += 1
                else:
                    logger.warning(f"FAIL: {name} failed but reason unclear: {response}")
                    failure_count += 1
            else:
                logger.error(f"FAIL: {name} succeeded but should have been rejected!")
                failure_count += 1

        logger.info(f"Test Complete. Passed: {success_count}, Failed: {failure_count}")
        self.assertEqual(failure_count, 0, "Some order types failed validation.")

if __name__ == "__main__":
    # Ensure database.token_db.get_token returns value
    sys.modules["database.token_db"].get_token.return_value = "12345"
    sys.modules["database.token_db"].get_br_symbol.return_value = "SBIN-EQ"

    unittest.main()
