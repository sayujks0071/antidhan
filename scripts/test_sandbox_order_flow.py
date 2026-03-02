import sys
import os
import json
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'openalgo')))

from app import app

def test_orders():
    client = app.test_client()

    order_types = [
        {"pricetype": "LIMIT", "price": "500", "trigger_price": "0"},
        {"pricetype": "MARKET", "price": "0", "trigger_price": "0"},
        {"pricetype": "STOP_LOSS", "price": "500", "trigger_price": "490"},
        {"pricetype": "STOP_LOSS_MARKET", "price": "0", "trigger_price": "490"},
        {"pricetype": "BO", "price": "500", "trigger_price": "490"}
    ]

    print("Running order flow diagnostic...\n")

    # We use diagnostic_order_flow.py approach, no need to mock everything if we can just patch `services.place_smart_order_service.place_order_service`
    with patch("services.place_smart_order_service.place_order_service") as mock_place_order:

        for order in order_types:
            rejected_response = {"status": "error", "message": "Order Rejected: Market is Closed"}
            mock_place_order.return_value = rejected_response

            payload = {
                "apikey": "test_api_key",
                "strategy": "Diagnostic",
                "symbol": "SBIN",
                "action": "BUY",
                "exchange": "NSE",
                "pricetype": order["pricetype"],
                "product": "MIS",
                "quantity": "1",
                "price": order["price"],
                "trigger_price": order["trigger_price"],
                "disclosed_quantity": "0",
            }

            print(f"Testing {order['pricetype']} Order...")
            response = client.post("/api/v1/placeorder", json=payload)

            print(f"Status Code: {response.status_code}")
            try:
                data = response.get_json()
                print(f"Response: {data}")
                if data and data.get("status") == "error" and "Rejected" in data.get("message", ""):
                    print(f"PASS: Handled rejected order for {order['pricetype']}\n")
                else:
                    print(f"FAIL: Expected explicit 'Rejected' error for {order['pricetype']}\n")
            except Exception as e:
                print(f"Failed to parse JSON: {e}\n")

if __name__ == "__main__":
    test_orders()
