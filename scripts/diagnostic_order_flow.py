#!/usr/bin/env python3
import sys
import os
import json
import logging
from unittest.mock import patch

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DiagnosticOrderFlow")

# Set dummy env vars for DB
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["BROKER_API_KEY"] = "dummy_key"
os.environ["API_KEY_PEPPER"] = "0" * 32
os.environ["FLASK_SECRET_KEY"] = "dummy_secret_key_at_least_32_chars_long"

# Add repo root to path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
openalgo_root = os.path.join(repo_root, "openalgo")

if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
if openalgo_root not in sys.path:
    sys.path.insert(0, openalgo_root)

try:
    from openalgo.services.place_smart_order_service import place_smart_order
    # We need to patch utils.httpx_client.request because that's what the broker api uses
    import openalgo.utils.httpx_client as httpx_client_module
except ImportError as e:
    logger.error(f"Failed to import modules: {e}")
    sys.exit(1)

class MockResponse:
    def __init__(self, json_data, status_code):
        self.json_data = json_data
        self.status_code = status_code
        self.text = json.dumps(json_data)
        self.status = status_code # Some code checks .status

    def json(self):
        return self.json_data

def mock_request(method, url, headers=None, content=None, max_retries=3):
    logger.info(f"[MOCK] Request: {method} {url}")
    if content:
        logger.info(f"[MOCK] Payload: {content}")

    # Simulate Dhan Sandbox Response for Market Closed
    # HTTP 200 OK, but orderStatus is REJECTED
    response_data = {
        "status": "success",
        "orderId": "1000001",
        "orderStatus": "REJECTED",
        "orderStatusMessage": "Market is Closed",
        "rejectReason": "Market is Closed"
    }
    return MockResponse(response_data, 200)

def run_diagnostic():
    logger.info("Starting Order Flow Diagnostic (Market Closed Simulation)...")

    # Order Types to Test
    order_types = [
        {"name": "LIMIT", "type": "LIMIT", "price": "500"},
        {"name": "MARKET", "type": "MARKET", "price": "0"},
        {"name": "SL", "type": "STOP_LOSS", "price": "500", "trigger_price": "490"},
        {"name": "SL-M", "type": "STOP_LOSS_MARKET", "price": "0", "trigger_price": "490"},
        {"name": "Bracket", "type": "BO", "price": "500", "trigger_price": "490", "stop_loss": "5", "take_profit": "10"}
    ]

    # Dummy Data
    symbol = "SBIN"
    exchange = "NSE"
    product = "MIS"
    api_key = "test_api_key"

    # Mock Token DB to return a valid token so validation passes
    # Note: The app imports 'broker' and 'database' as top-level packages
    with patch('database.token_db.get_token', return_value="1333"), \
         patch('openalgo.services.place_smart_order_service.get_token', return_value="1333"), \
         patch('broker.dhan_sandbox.api.order_api.get_token', return_value="1333"), \
         patch('broker.dhan_sandbox.api.order_api.get_open_position', return_value="0"):

        # Mock Auth DB to return a valid auth token
        with patch('openalgo.services.place_smart_order_service.get_auth_token_broker', return_value=("mock_auth_token", "dhan_sandbox")):
            # Mock get_analyze_mode to False (Live/Paper Trading)
            with patch('openalgo.services.place_smart_order_service.get_analyze_mode', return_value=False):
                # Mock executor to prevent DB writes
                with patch('openalgo.services.place_smart_order_service.executor.submit'):
                    # Mock httpx request (patching local import in order_api)
                    with patch('broker.dhan_sandbox.api.order_api.request', side_effect=mock_request):

                        failed_count = 0
                        success_handled_count = 0

                        for order_conf in order_types:
                            logger.info(f"\n--- Testing Order Type: {order_conf['name']} ---")

                            order_data = {
                                "symbol": symbol,
                                "exchange": exchange,
                                "action": "BUY",
                                "quantity": "1",
                                "pricetype": order_conf['type'],
                                "product": product,
                                "price": order_conf['price'],
                                "trigger_price": order_conf.get('trigger_price', '0'),
                                "disclosed_quantity": "0",
                                "apikey": api_key,
                                "strategy": "Diagnostic",
                                "position_size": "1"
                            }

                            # Call the service
                            # Note: place_smart_order returns (success, response, status_code)
                            success, response, status_code = place_smart_order(
                                order_data=order_data,
                                api_key=api_key
                            )

                            logger.info(f"Service Result: Success={success}, Status={status_code}")
                            logger.info(f"Response: {response}")

                            # Verification Logic
                            # We EXPECT the service to return success=False because the order was REJECTED by broker
                            # even though HTTP status was 200.
                            # However, place_smart_order_service implementation says:
                            # if res and res.status == 200:
                            #    if order_id is None: return False, ...
                            #    else: return True, ...

                            # In our mock, we return "orderId": "1000001".
                            # But we also set "orderStatus": "REJECTED".

                            # Let's see how `broker.dhan_sandbox.api.order_api.place_order_api` handles it.
                            # It checks: if order_status in ["REJECTED", "FAILED"]: orderid = None

                            # So place_order_api should return orderid=None.
                            # Then place_smart_order_service should see order_id is None and return False.

                            if not success:
                                logger.info("PASS: Service correctly identified failure.")
                                success_handled_count += 1
                            else:
                                logger.error("FAIL: Service reported success for a REJECTED order!")
                                failed_count += 1

                        logger.info("\n--- Diagnostic Summary ---")
                    logger.info(f"Total Tests: {len(order_types)}")
                    logger.info(f"Correctly Handled (Rejected): {success_handled_count}")
                    logger.info(f"Incorrectly Handled (Success): {failed_count}")

                    if failed_count > 0:
                        sys.exit(1)
                    else:
                        sys.exit(0)

if __name__ == "__main__":
    run_diagnostic()
