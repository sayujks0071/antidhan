import sys
import os
import json
import logging
from unittest.mock import patch, MagicMock

# Add repo root to path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.append(repo_root)
    sys.path.append(os.path.join(repo_root, 'openalgo'))

# Imports
try:
    from openalgo.broker.dhan_sandbox.api.order_api import place_order_api
    import openalgo.broker.dhan_sandbox.api.order_api as order_api_module
except ImportError:
    # Handle direct execution from scripts/
    sys.path.append(os.path.join(repo_root, 'openalgo'))
    from broker.dhan_sandbox.api.order_api import place_order_api
    import broker.dhan_sandbox.api.order_api as order_api_module

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DiagnosticOrders")

def mock_get_token(symbol, exchange):
    return "1333"

def run_diagnostic():
    logger.info("Starting Order Flow Diagnostic (Market Closed Simulation)...")

    auth_token = "test_token"
    if not os.getenv("BROKER_API_KEY"):
        os.environ["BROKER_API_KEY"] = "test_client_id"

    symbol = "SBIN"
    exchange = "NSE"

    # 5 Order Types
    orders = [
        {"type": "LIMIT", "price": 500, "trigger_price": 0, "product": "MIS"},
        {"type": "MARKET", "price": 0, "trigger_price": 0, "product": "MIS"},
        {"type": "SL", "price": 500, "trigger_price": 490, "product": "MIS"},
        {"type": "SL-M", "price": 0, "trigger_price": 490, "product": "MIS"},
        {"type": "BO", "price": 500, "trigger_price": 0, "product": "MIS", "stop_loss": 5, "take_profit": 10}
    ]

    # Patch get_token
    with patch.object(order_api_module, 'get_token', side_effect=mock_get_token):

        # Patch request to return Market Closed rejection
        def mock_request(method, url, headers=None, content=None, max_retries=3):
            logger.info(f"Mock Request: {method} {url}")

            # Simulate Dhan Response for Market Closed
            # Dhan returns 200 OK even for rejection, with status in body
            response_dict = {
                "status": "success",
                "remarks": "Market Closed",
                "data": {
                    "orderId": "1000001",
                    "orderStatus": "REJECTED",
                    "rejectReason": "Market is Closed",
                    "remarks": "Market is Closed"
                },
                "orderId": "1000001",
                "orderStatus": "REJECTED"
            }

            class MockResponse:
                def __init__(self, json_data, status_code):
                    self.json_data = json_data
                    self.status_code = status_code
                    self.text = json.dumps(json_data)

                def json(self):
                    return self.json_data

            return MockResponse(response_dict, 200)

        with patch.object(order_api_module, 'request', side_effect=mock_request):

            for i, order_conf in enumerate(orders):
                logger.info(f"\n--- Test {i+1}: {order_conf['type']} ---")

                order_data = {
                    "symbol": symbol,
                    "exchange": exchange,
                    "action": "BUY",
                    "quantity": "1",
                    "pricetype": order_conf['type'],
                    "product": order_conf['product'],
                    "price": str(order_conf['price']),
                    "trigger_price": str(order_conf['trigger_price']),
                    "disclosed_quantity": "0",
                    "tag": "diagnostic"
                }

                if order_conf['type'] == 'BO':
                    order_data['bo_stop_loss_value'] = order_conf.get('stop_loss')
                    order_data['bo_profit_value'] = order_conf.get('take_profit')

                try:
                    res, response_data, orderid = place_order_api(order_data, auth_token)

                    logger.info(f"Order API Response Data: {response_data}")

                    # Verification Logic
                    # order_api.py returns orderid=None if status is REJECTED
                    if orderid is None:
                        logger.info("✅ Correctly detected rejection (Order ID is None)")
                        msg = response_data.get('message', '')
                        if "Market is Closed" in msg or "Rejected" in msg:
                             logger.info(f"✅ Rejection reason captured: {msg}")
                        else:
                             logger.warning(f"⚠️ Rejection reason might be unclear: {msg}")
                    else:
                        # If it returned an order ID, check if it warned
                        logger.warning(f"❌ Failed to detect rejection! Returned Order ID: {orderid}")
                        logger.info(f"Response Data Status: {response_data.get('orderStatus')}")

                except Exception as e:
                    logger.error(f"Exception: {e}", exc_info=True)

if __name__ == "__main__":
    run_diagnostic()
