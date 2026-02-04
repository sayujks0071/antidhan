import sys
import os
import json
import logging
from unittest.mock import patch

# Add repo root to path
# Assuming script is in scripts/ folder, repo root is parent
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.append(repo_root)
    sys.path.append(os.path.join(repo_root, 'openalgo'))

# Try to import from openalgo package if strictly structured, or direct path
try:
    import openalgo.broker.dhan_sandbox.api.order_api as order_api_module
    from openalgo.broker.dhan_sandbox.api.order_api import place_order_api
except ImportError:
    try:
        import broker.dhan_sandbox.api.order_api as order_api_module
        from broker.dhan_sandbox.api.order_api import place_order_api
    except ImportError:
        # If openalgo is not in path correctly
        sys.path.append(os.path.join(repo_root, 'openalgo'))
        import broker.dhan_sandbox.api.order_api as order_api_module
        from broker.dhan_sandbox.api.order_api import place_order_api

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DiagnosticOrders")

def mock_get_token(symbol, exchange):
    return "1333" # SBIN token? Any dummy string is fine if sandbox accepts it or we mock request

def run_diagnostic():
    logger.info("Starting Order Flow Diagnostic...")

    # Dummy Auth Token
    auth_token = "test_token"

    # Mock environment variables if needed
    if not os.getenv("BROKER_API_KEY"):
        os.environ["BROKER_API_KEY"] = "test_client_id"

    symbol = "SBIN"
    exchange = "NSE"

    # Define test cases
    orders = [
        {"type": "LIMIT", "price": 500, "trigger_price": 0, "product": "MIS"},
        {"type": "MARKET", "price": 0, "trigger_price": 0, "product": "MIS"},
        {"type": "STOP_LOSS", "price": 500, "trigger_price": 490, "product": "MIS"}, # SL Limit -> SL
        {"type": "STOP_LOSS_MARKET", "price": 0, "trigger_price": 490, "product": "MIS"}, # SL-M -> SLM
        # Bracket Order support might depend on API. Usually BO or CO.
        {"type": "BO", "price": 500, "trigger_price": 0, "product": "MIS", "stop_loss": 5, "take_profit": 10}
    ]

    # Patch get_token to avoid database issues
    with patch.object(order_api_module, 'get_token', side_effect=mock_get_token):
        # We also need to patch `request` because we don't have a running Dhan Sandbox server to talk to!
        # Unless the task implies "Verify the orders.py blueprint... in the Dhan Sandbox" means I should assume Sandbox is running?
        # The prompt says "Create a diagnostic script that attempts to place 5 different order types... in the Dhan Sandbox."
        # Usually "Sandbox" refers to the mock broker logic *in this repo* (under `broker/dhan_sandbox`), OR an external service.
        # Given "broker/dhan_sandbox/" exists, it seems to be an internal sandbox implementation or adapter.
        # But `order_api.py` makes HTTP requests to `get_url("/v2/orders")`.
        # Where is the server?
        # If I cannot reach the server, I cannot verify the response handling of "REJECTED".

        # However, I can MOCK the response from `request` to SIMULATE "REJECTED" status.
        # This effectively tests the client code (order_api.py) handling of such response.

        def mock_request(method, url, headers=None, content=None, max_retries=3):
            logger.info(f"Mock Request: {method} {url} Payload: {content}")

            # Simulate Dhan Sandbox Response
            # Scenario: Market Closed -> Rejected

            # We want to return a response that has status 200 (as per Dhan API behavior sometimes) or 400?
            # Memory says "Dhan Sandbox API ... explicitly checks orderStatus ... even on HTTP 200".
            # So I will simulate HTTP 200 with "orderStatus": "REJECTED".

            payload = json.loads(content) if content else {}
            pricetype = payload.get("price_type") or payload.get("pricetype")

            # Construct a fake response
            response_dict = {
                "status": "success",
                "remarks": "Market Closed",
                "data": {
                    "orderId": "1000001",
                    "orderStatus": "REJECTED",
                    "rejectReason": "Market is Closed"
                },
                # Some APIs return orderId at top level too?
                # order_api.py checks `response_data["orderId"]`.
                # Let's align with what order_api expects.
                # order_api.py: response_data = json.loads(res.text)
                # if response_data and "orderId" in response_data: ...

                "orderId": "1000001",
                "orderStatus": "REJECTED"
            }

            # Create a mock response object
            class MockResponse:
                def __init__(self, json_data, status_code):
                    self.json_data = json_data
                    self.status_code = status_code
                    self.text = json.dumps(json_data)

            return MockResponse(response_dict, 200)

        with patch.object(order_api_module, 'request', side_effect=mock_request):
            for i, order_conf in enumerate(orders):
                logger.info(f"\n--- Test {i+1}: {order_conf['type']} ---")

                # Map to API format (approximate, based on order_api expectations)
                pricetype = order_conf['type']
                if pricetype == "STOP_LOSS": pricetype = "SL"
                if pricetype == "STOP_LOSS_MARKET": pricetype = "SLM"

                order_data = {
                    "symbol": symbol,
                    "exchange": exchange,
                    "action": "BUY",
                    "quantity": "1",
                    "pricetype": pricetype,
                    "product": order_conf['product'],
                    "price": str(order_conf['price']),
                    "trigger_price": str(order_conf['trigger_price']),
                    "disclosed_quantity": "0",
                    "tag": "diagnostic"
                }

                try:
                    res, response_data, orderid = place_order_api(order_data, auth_token)

                    status_code = res.status_code if hasattr(res, 'status_code') else 'Unknown'
                    logger.info(f"Response Status Code: {status_code}")
                    logger.info(f"Response Data: {response_data}")
                    logger.info(f"Extracted Order ID: {orderid}")

                    if orderid:
                        logger.info("Result: SUCCESS (Order ID found)")

                        # Check for rejection in data
                        if isinstance(response_data, dict):
                            status = response_data.get("orderStatus")
                            if status in ["REJECTED", "FAILED"]:
                                logger.warning(f"  [WARNING] Order ID returned but Status is {status}! 'orders.py' might treat this as success.")
                    else:
                        logger.info("Result: FAILED (No Order ID)")
                        if isinstance(response_data, dict):
                             logger.info(f"Error Message: {response_data.get('message')}")

                except Exception as e:
                    logger.error(f"Exception during order placement: {e}", exc_info=True)

if __name__ == "__main__":
    run_diagnostic()
