import sys
import os

# Add the openalgo directory to the sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'openalgo')))

try:
    from app import app
    from database.user_db import get_or_create_user
except ImportError as e:
    print(f"Failed to import from openalgo: {e}")
    sys.exit(1)

def test_orders():
    client = app.test_client()

    with app.app_context():
        # Get an API Key to use in the requests
        user, _ = get_or_create_user("admin")
        api_key = user.api_key

    # Types to test
    order_types = [
        {"pricetype": "LIMIT", "price": "500", "trigger_price": "0"},
        {"pricetype": "MARKET", "price": "0", "trigger_price": "0"},
        {"pricetype": "STOP_LOSS", "price": "500", "trigger_price": "490"},
        {"pricetype": "STOP_LOSS_MARKET", "price": "0", "trigger_price": "490"},
        {"pricetype": "BO", "price": "500", "trigger_price": "490"} # Bracket Order
    ]

    for order in order_types:
        payload = {
            "apikey": api_key,
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
