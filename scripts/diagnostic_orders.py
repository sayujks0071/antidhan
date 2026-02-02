#!/usr/bin/env python3
"""
Diagnostic script to simulate order flow and verify error handling.
"""
import os
import sys
import json
import logging
from unittest.mock import MagicMock, patch

# Setup paths
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
openalgo_dir = os.path.join(root_dir, 'openalgo')
sys.path.insert(0, openalgo_dir)
sys.path.insert(0, root_dir)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DiagnosticOrders")

# Mock environment variables
os.environ["BROKER_API_KEY"] = "test_client_id"
os.environ["API_KEY_PEPPER"] = "mock_pepper_for_test_which_is_long_enough_to_pass_validation_check_123"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Debug imports
try:
    import utils
    print(f"DEBUG: imported utils from {utils.__file__}")
    import utils.httpx_client
    print(f"DEBUG: imported utils.httpx_client from {utils.httpx_client.__file__}")
except Exception as e:
    print(f"DEBUG: Import error: {e}")

# Mock dependencies before importing modules that use them
# We need to mock utils.httpx_client.request used by order_api.py

def mock_request(method, url, headers=None, content=None, max_retries=3, backoff_factor=1.0):
    logger.info(f"Mock Request: {method} {url}")
    logger.debug(f"Payload: {content}")

    # Simulate Dhan Sandbox Responses
    payload = {}
    if content:
        try:
            payload = json.loads(content)
        except Exception:
            pass

    # 1. Successful Order (Price 500)
    if payload.get("price") == 500.0:
        response = MagicMock()
        response.status_code = 200
        response.text = json.dumps({
            "orderId": "1001",
            "orderStatus": "PENDING",
            "status": "success"
        })
        return response

    # 2. Rejected Order (Market Closed) - Scenario 1: 200 OK but status failed (Price 0, Qty 10)
    if payload.get("price") == 0.0 and payload.get("quantity") == 10:
        response = MagicMock()
        response.status_code = 200
        # Dhan usually returns status=success with orderId even if it gets rejected later via websocket
        # BUT if it is rejected synchronously, it might return status=failure or similar.
        # The prompt says: "even if the status is instantly 'REJECTED'"
        # Let's assume it returns success with orderId, but maybe orderStatus is REJECTED in the response data if available?
        # Or maybe it returns status='failure'?
        # Let's test the case where it returns success but orderStatus is REJECTED.

        response.text = json.dumps({
            "orderId": "1002",
            "orderStatus": "REJECTED",
            "status": "success", # API call success, but order rejected logic
            "data": {"message": "Market Closed"}
        })
        return response

    # 3. Rejected Order - Scenario 2: 400 Bad Request (Price 490)
    if payload.get("price") == 490.0:
        response = MagicMock()
        response.status_code = 400
        response.text = json.dumps({
            "status": "error",
            "errorCode": "INVALID_MARKET_STATUS",
            "errorMessage": "Market is closed"
        })
        return response

    # 4. Get Position (Success)
    if "positions" in url and method == "GET":
        response = MagicMock()
        response.status_code = 200
        response.text = json.dumps([
            {
                "tradingSymbol": "SBIN",
                "exchangeSegment": "NSE_EQ",
                "productType": "INTRADAY", # Mapped to MIS
                "netQty": 0
            }
        ])
        return response

    # Default fallback
    response = MagicMock()
    response.status_code = 200
    response.text = json.dumps({"status": "success"})
    return response

# Apply patch
# We patch 'utils.httpx_client.request' where 'utils' is the package we just imported
patcher = patch('utils.httpx_client.request', side_effect=mock_request)
patcher.start()

# Mock get_token and get_br_symbol to avoid DB dependency
def mock_get_token(symbol, exchange):
    return "12345"

def mock_get_br_symbol(symbol, exchange):
    return symbol

# Now import the module to test
try:
    from openalgo.broker.dhan_sandbox.api import order_api
    order_api.get_token = mock_get_token
    order_api.get_br_symbol = mock_get_br_symbol
    order_api.get_open_position = MagicMock(return_value=0) # Also mock get_open_position to simplify
    place_smartorder_api = order_api.place_smartorder_api
    place_order_api = order_api.place_order_api
except ImportError:
    # Try alternate path if running from root
    from broker.dhan_sandbox.api import order_api
    order_api.get_token = mock_get_token
    order_api.get_br_symbol = mock_get_br_symbol
    order_api.get_open_position = MagicMock(return_value=0)
    place_smartorder_api = order_api.place_smartorder_api
    place_order_api = order_api.place_order_api

def run_diagnostics():
    auth_token = "test_token"

    test_cases = [
        {
            "name": "Limit Order (Success)",
            "data": {
                "symbol": "SBIN", "exchange": "NSE", "action": "BUY", "product": "MIS",
                "pricetype": "LIMIT", "quantity": "10", "price": "500", "trigger_price": "0",
                "disclosed_quantity": "0", "position_size": "0", "tag": "place_success"
            },
            "expected_success": True
        },
        {
            "name": "Market Order (Rejection 200 OK)",
            "data": {
                "symbol": "SBIN", "exchange": "NSE", "action": "BUY", "product": "MIS",
                "pricetype": "MARKET", "quantity": "10", "price": "0", "trigger_price": "0",
                "disclosed_quantity": "0", "position_size": "0", "tag": "place_reject_200"
            },
            "expected_success": False
        },
        {
            "name": "SL Order (Rejection 400)",
            "data": {
                "symbol": "SBIN", "exchange": "NSE", "action": "SELL", "product": "MIS",
                "pricetype": "SL", "quantity": "10", "price": "490", "trigger_price": "495",
                "disclosed_quantity": "0", "position_size": "0", "tag": "place_reject_400"
            },
            "expected_success": False
        }
    ]

    print("Starting Diagnostics...")
    print("-" * 60)

    for case in test_cases:
        print(f"Testing: {case['name']}")
        data = case['data']

        # We call place_smartorder_api which calls place_order_api
        res, response, orderid = place_smartorder_api(data, auth_token)

        print(f"  Response Status: {res.status_code if res else 'None'}")
        print(f"  Response Data: {response}")
        print(f"  OrderId: {orderid}")

        # Simulate logic in orders.py
        # Logic: if orderid: success else: failure

        orders_py_result = "SUCCESS" if orderid else "FAILURE"
        print(f"  orders.py interpretation: {orders_py_result}")

        if case['expected_success'] and orders_py_result == "SUCCESS":
            print("  [PASS] Correctly handled success.")
        elif not case['expected_success'] and orders_py_result == "FAILURE":
             print("  [PASS] Correctly handled failure.")
        elif not case['expected_success'] and orders_py_result == "SUCCESS":
             print("  [FAIL] orders.py would report SUCCESS but order was REJECTED!")
             # This confirms the bug if place_order_api returns orderid for rejected orders
        else:
             print("  [FAIL] Unexpected outcome.")

        print("-" * 60)

if __name__ == "__main__":
    try:
        run_diagnostics()
    finally:
        patcher.stop()
