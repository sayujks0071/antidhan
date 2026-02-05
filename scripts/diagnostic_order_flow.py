import sys
import os
import json
import logging
import unittest
from unittest.mock import patch, MagicMock

# Set required env vars for auth_db import to prevent crashes
os.environ["API_KEY_PEPPER"] = "a" * 32  # Must be at least 32 chars
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Add repo root to path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.append(repo_root)
    sys.path.append(os.path.join(repo_root, 'openalgo'))

try:
    import openalgo.broker.dhan_sandbox.api.order_api as order_api_module
    from openalgo.broker.dhan_sandbox.api.order_api import place_order_api
except ImportError:
    # Try alternate path if package structure varies
    sys.path.append(os.path.join(repo_root, 'openalgo'))
    import broker.dhan_sandbox.api.order_api as order_api_module
    from broker.dhan_sandbox.api.order_api import place_order_api

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("OrderFlowDiag")

def mock_get_token(symbol, exchange):
    return "1333"

class TestOrderFlow(unittest.TestCase):

    def setUp(self):
        self.auth_token = "test_token"
        os.environ["BROKER_API_KEY"] = "test_client_id"
        self.symbol = "SBIN"
        self.exchange = "NSE"

    # Patch where place_order_api looks for request
    @patch('openalgo.broker.dhan_sandbox.api.order_api.request')
    @patch('openalgo.broker.dhan_sandbox.api.order_api.get_token', side_effect=mock_get_token)
    def test_market_closed_rejection(self, mock_token, mock_request):
        """
        Verify that if the broker returns 'REJECTED' (e.g. Market Closed),
        place_order_api returns None for order_id.
        """
        logger.info("Testing Market Closed / Rejected Scenario...")

        # Mock Response for REJECTED order
        response_dict = {
            "status": "success",
            "remarks": "Market Closed",
            "data": {
                "orderId": "1000001",
                "orderStatus": "REJECTED",
                "rejectReason": "Market is Closed"
            },
            "orderId": "1000001",
            "orderStatus": "REJECTED"
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps(response_dict)
        mock_resp.json.return_value = response_dict
        mock_request.return_value = mock_resp

        # Test 5 Order Types
        order_types = [
            {"type": "LIMIT", "price": 500, "trigger_price": 0, "product": "MIS"},
            {"type": "MARKET", "price": 0, "trigger_price": 0, "product": "MIS"},
            {"type": "SL", "price": 500, "trigger_price": 490, "product": "MIS"},
            {"type": "SLM", "price": 0, "trigger_price": 490, "product": "MIS"},
            {"type": "BO", "price": 500, "trigger_price": 0, "product": "MIS"}
        ]

        for i, conf in enumerate(order_types):
            logger.info(f"Testing Order Type: {conf['type']}")
            order_data = {
                "symbol": self.symbol,
                "exchange": self.exchange,
                "action": "BUY",
                "quantity": "1",
                "pricetype": conf['type'],
                "product": conf['product'],
                "price": str(conf['price']),
                "trigger_price": str(conf['trigger_price']),
                "disclosed_quantity": "0"
            }

            res, response_data, orderid = place_order_api(order_data, self.auth_token)

            logger.info(f"  Response Status: {response_data.get('orderStatus')}")
            logger.info(f"  Returned Order ID: {orderid}")

            # ASSERTION: orderid should be None because status is REJECTED
            self.assertIsNone(orderid, f"Order ID should be None for REJECTED order type {conf['type']}")
            self.assertEqual(response_data.get('orderStatus'), 'REJECTED')

    @patch('openalgo.broker.dhan_sandbox.api.order_api.request')
    @patch('openalgo.broker.dhan_sandbox.api.order_api.get_token', side_effect=mock_get_token)
    def test_order_success(self, mock_token, mock_request):
        """
        Verify that if the broker returns 'PENDING' or 'TRADED',
        place_order_api returns the order_id.
        """
        logger.info("Testing Success Scenario...")

        response_dict = {
            "status": "success",
            "data": {
                "orderId": "1000002",
                "orderStatus": "PENDING"
            },
            "orderId": "1000002",
            "orderStatus": "PENDING"
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps(response_dict)
        mock_resp.json.return_value = response_dict
        mock_request.return_value = mock_resp

        order_data = {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "action": "BUY",
            "quantity": "1",
            "pricetype": "LIMIT",
            "product": "MIS",
            "price": "500",
            "trigger_price": "0",
            "disclosed_quantity": "0"
        }

        res, response_data, orderid = place_order_api(order_data, self.auth_token)

        self.assertEqual(orderid, "1000002", "Order ID should be returned for PENDING order")

if __name__ == "__main__":
    unittest.main()
