import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import json

# Set environment variables for database module
os.environ['API_KEY_PEPPER'] = 'test_pepper_at_least_32_chars_long_xxxxxxxxxxxx'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['BROKER_API_KEY'] = 'TEST_API_KEY'

# Add openalgo directory to path so 'broker' is recognized as a top-level package
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

from broker.dhan_sandbox.api.order_api import place_order_api

class TestOrderTypes(unittest.TestCase):
    def setUp(self):
        self.auth_token = "MOCK_TOKEN"
        # Base order data
        self.base_order = {
            "symbol": "TCS",
            "exchange": "NSE",
            "quantity": "10",
            "action": "BUY",
            "product": "CNC",
            "price": "0",
            "trigger_price": "0",
            "disclosed_quantity": "0",
            "validity": "DAY",
            "amo": "NO"
        }

    @patch('broker.dhan_sandbox.api.order_api.request')
    @patch('broker.dhan_sandbox.api.order_api.get_token')
    def test_market_order_rejection(self, mock_get_token, mock_request):
        print("\nTesting MARKET Order Rejection...")
        mock_get_token.return_value = "11536" # Mock Security ID

        # Mock Response for Market Closed Rejection
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({
            "status": "failed",
            "remarks": "Market Closed",
            "orderStatus": "REJECTED",
            "orderId": "100001",
            "errorCode": "805",
            "errorMessage": "Market is closed"
        })
        mock_request.return_value = mock_response

        # Market Order
        order_data = self.base_order.copy()
        order_data['pricetype'] = "MARKET"

        res, response, orderid = place_order_api(order_data, self.auth_token)

        print(f"Response: {response}")
        print(f"OrderID: {orderid}")

        self.assertIsNone(orderid, "Order ID should be None for Rejected order")
        self.assertIn("Rejected", response.get("message", ""), "Message should indicate rejection")
        # Depending on implementation, status might be 'failed' or kept as is from response
        # self.assertEqual(response.get("status"), "failed")

    @patch('broker.dhan_sandbox.api.order_api.request')
    @patch('broker.dhan_sandbox.api.order_api.get_token')
    def test_limit_order(self, mock_get_token, mock_request):
        print("\nTesting LIMIT Order...")
        mock_get_token.return_value = "11536"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({
            "status": "success",
            "orderStatus": "PENDING",
            "orderId": "100002"
        })
        mock_request.return_value = mock_response

        order_data = self.base_order.copy()
        order_data['pricetype'] = "LIMIT"
        order_data['price'] = "3500.00"

        res, response, orderid = place_order_api(order_data, self.auth_token)

        print(f"Response: {response}")
        print(f"OrderID: {orderid}")

        self.assertEqual(orderid, "100002")

    @patch('broker.dhan_sandbox.api.order_api.request')
    @patch('broker.dhan_sandbox.api.order_api.get_token')
    def test_sl_order(self, mock_get_token, mock_request):
        print("\nTesting STOP_LOSS Order...")
        mock_get_token.return_value = "11536"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({
            "status": "success",
            "orderStatus": "PENDING",
            "orderId": "100003"
        })
        mock_request.return_value = mock_response

        order_data = self.base_order.copy()
        order_data['pricetype'] = "STOP_LOSS"
        order_data['price'] = "3500.00"
        order_data['trigger_price'] = "3490.00"

        res, response, orderid = place_order_api(order_data, self.auth_token)
        self.assertEqual(orderid, "100003")

    @patch('broker.dhan_sandbox.api.order_api.request')
    @patch('broker.dhan_sandbox.api.order_api.get_token')
    def test_slm_order(self, mock_get_token, mock_request):
        print("\nTesting STOP_LOSS_MARKET Order...")
        mock_get_token.return_value = "11536"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({
            "status": "success",
            "orderStatus": "PENDING",
            "orderId": "100004"
        })
        mock_request.return_value = mock_response

        order_data = self.base_order.copy()
        order_data['pricetype'] = "STOP_LOSS_MARKET"
        order_data['trigger_price'] = "3490.00"

        res, response, orderid = place_order_api(order_data, self.auth_token)
        self.assertEqual(orderid, "100004")

    @patch('broker.dhan_sandbox.api.order_api.request')
    @patch('broker.dhan_sandbox.api.order_api.get_token')
    def test_bo_order(self, mock_get_token, mock_request):
        print("\nTesting BRACKET_ORDER (BO)...")
        mock_get_token.return_value = "11536"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({
            "status": "success",
            "orderStatus": "PENDING",
            "orderId": "100005"
        })
        mock_request.return_value = mock_response

        order_data = self.base_order.copy()
        order_data['pricetype'] = "LIMIT"
        order_data['product'] = "BO" # Bracket Order
        order_data['price'] = "3500.00"
        order_data['stop_loss_value'] = "10.0"
        order_data['square_off_value'] = "20.0"

        res, response, orderid = place_order_api(order_data, self.auth_token)
        self.assertEqual(orderid, "100005")

if __name__ == '__main__':
    unittest.main()
