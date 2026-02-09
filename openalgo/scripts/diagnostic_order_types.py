
import os
import sys
import logging
import unittest
from unittest.mock import MagicMock, patch

# Set dummy DATABASE_URL to avoid sqlalchemy error during import
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Add repo root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
openalgo_root = os.path.dirname(script_dir)
if openalgo_root not in sys.path:
    sys.path.insert(0, openalgo_root)

# Mocking database modules to avoid connection errors during import
sys.modules["database.analyzer_db"] = MagicMock()
sys.modules["database.apilog_db"] = MagicMock()
sys.modules["database.auth_db"] = MagicMock()
sys.modules["database.token_db"] = MagicMock()
sys.modules["database.symbol"] = MagicMock()
sys.modules["extensions"] = MagicMock()
sys.modules["services.telegram_alert_service"] = MagicMock()
sys.modules["pytz"] = MagicMock()
sys.modules["sqlalchemy"] = MagicMock()
sys.modules["h2"] = MagicMock()
sys.modules["structlog"] = MagicMock()
sys.modules["httpx"] = MagicMock()
sys.modules["cachetools"] = MagicMock()
sys.modules['openalgo_observability'] = MagicMock()
sys.modules['openalgo_observability.logging_setup'] = MagicMock()

# Configure settings_db mock BEFORE importing service
settings_db_mock = MagicMock()
settings_db_mock.get_analyze_mode.return_value = False
sys.modules["database.settings_db"] = settings_db_mock

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DiagnosticOrderTypes")

from services.place_smart_order_service import place_smart_order

class TestOrderFlow(unittest.TestCase):
    @patch("services.place_smart_order_service.import_broker_module")
    def test_rejected_orders(self, mock_import):
        """
        Simulate placing 5 order types and receiving REJECTED status.
        Verifies that 'None' order_id is correctly handled as failure.
        """
        # Mock broker module
        mock_broker = MagicMock()
        mock_import.return_value = mock_broker

        # Mock API response for REJECTED order (Market Closed)
        mock_res = MagicMock()
        mock_res.status = 200

        mock_response_data = {
            "status": "failure",
            "orderStatus": "REJECTED",
            "message": "Market Closed",
            "orderId": "12345"
        }

        # place_smartorder_api returns (res, response_data, order_id)
        # order_id is None because it was rejected
        mock_broker.place_smartorder_api.return_value = (mock_res, mock_response_data, None)

        order_types = ["LIMIT", "MARKET", "STOP_LOSS", "STOP_LOSS_MARKET", "BRACKET_ORDER"]

        for order_type in order_types:
            logger.info(f"Testing Order Type: {order_type}")

            order_data = {
                "apikey": "mock_api_key",
                "strategy": "Diagnostic",
                "symbol": "SBIN",
                "exchange": "NSE",
                "action": "BUY",
                "quantity": 1,
                "position_size": 1,
                "price_type": order_type if order_type in ["LIMIT", "MARKET", "STOP_LOSS", "STOP_LOSS_MARKET"] else "LIMIT",
                "product_type": "MIS",
                "price": 100
            }

            # Use auth_token and broker arguments to bypass DB lookup
            success, response, status_code = place_smart_order(
                order_data,
                auth_token="mock_token",
                broker="dhan_sandbox"
            )

            logger.info(f"Response: Success={success}, Status={status_code}, Data={response}")

            # Verification
            if success:
                 if response.get("orderid") is None:
                     logger.error(f"FAILURE: Order {order_type} returned SUCCESS but orderid is None! This mimics the 'Market Closed' bug.")
                     self.fail(f"Order {order_type} was rejected (None ID) but service returned Success.")
                 else:
                     logger.info(f"Order {order_type} Accepted (Mocked). ID: {response.get('orderid')}")
            else:
                 logger.info(f"Order {order_type} Correctly Reported Failure: {response.get('message')}")

if __name__ == "__main__":
    unittest.main()
