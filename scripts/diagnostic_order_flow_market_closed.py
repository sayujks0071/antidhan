import sys
import os
import unittest
from unittest.mock import MagicMock
from flask import Flask

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'openalgo'))

# Mock database and other dependencies
sys.modules['database'] = MagicMock()
sys.modules['database.auth_db'] = MagicMock()
sys.modules['database.token_db'] = MagicMock()
sys.modules['database.settings_db'] = MagicMock()
sys.modules['database.apilog_db'] = MagicMock()
sys.modules['database.analyzer_db'] = MagicMock()
sys.modules['database.action_center_db'] = MagicMock()
sys.modules['database.symbol'] = MagicMock()
sys.modules['extensions'] = MagicMock()
sys.modules['limiter'] = MagicMock()
sys.modules['utils.session'] = MagicMock()

# Mock limiter object
limiter_mock = MagicMock()
limiter_mock.limit = lambda x: lambda f: f
sys.modules['limiter'].limiter = limiter_mock

# Mock session decorator
def check_session_validity(f):
    return f
sys.modules['utils.session'].check_session_validity = check_session_validity

sys.modules['services.telegram_alert_service'] = MagicMock()
sys.modules['services.order_router_service'] = MagicMock()

# Setup common mocks
from database.auth_db import get_auth_token, get_api_key_for_tradingview
from database.token_db import get_token
from database.settings_db import get_analyze_mode

get_auth_token.return_value = "DUMMY_TOKEN"
get_api_key_for_tradingview.return_value = "TEST_API_KEY"
get_token.return_value = "12345"
get_analyze_mode.return_value = False

# Mock order router
from services.order_router_service import should_route_to_pending
should_route_to_pending.return_value = False

# Mock broker
broker_mock = MagicMock()
sys.modules['broker'] = MagicMock()
sys.modules['broker.dhan_sandbox'] = MagicMock()
sys.modules['broker.dhan_sandbox.api'] = MagicMock()
sys.modules['broker.dhan_sandbox.api.order_api'] = broker_mock

# Now imports
# We can't easily import the full app because it imports everything.
# We can import the blueprint and register it on a fresh Flask app.
from openalgo.blueprints.orders import orders_bp

app = Flask(__name__)
app.secret_key = "secret"
app.register_blueprint(orders_bp)

class MockResponse:
    def __init__(self, status_code):
        self.status = status_code
        self.status_code = status_code

def run_diagnostic():
    print("Starting Diagnostic: Order Flow Blueprint (Market Closed)...")

    # Mock response for rejection
    broker_mock.place_smartorder_api.return_value = (
        MockResponse(200),
        {
            "status": "failure",
            "remarks": "Market is Closed",
            "orderStatus": "REJECTED",
            "message": "Order Rejected: Market is Closed"
        },
        None
    )

    test_orders = [
        {"strategy": "Diag", "position_size": 1, "symbol": "INFY", "exchange": "NSE", "action": "BUY", "quantity": 1, "price_type": "LIMIT", "price": 1500, "product": "MIS"},
        {"strategy": "Diag", "position_size": 5, "symbol": "TCS", "exchange": "NSE", "action": "SELL", "quantity": 5, "price_type": "MARKET", "product": "CNC"},
        {"strategy": "Diag", "position_size": 50, "symbol": "NIFTY", "exchange": "NSE", "action": "BUY", "quantity": 50, "price_type": "SL", "price": 18000, "trigger_price": 17900, "product": "NRML"},
        {"strategy": "Diag", "position_size": 10, "symbol": "RELIANCE", "exchange": "NSE", "action": "SELL", "quantity": 10, "price_type": "SL-M", "trigger_price": 2500, "product": "MIS"},
        {"strategy": "Diag", "position_size": 100, "symbol": "SBIN", "exchange": "NSE", "action": "BUY", "quantity": 100, "price_type": "LIMIT", "price": 600, "product": "BO", "stop_loss": 5, "square_off": 10}
    ]

    client = app.test_client()
    passed = 0
    failed = 0

    with client.session_transaction() as sess:
        sess['user'] = 'testuser'
        sess['broker'] = 'dhan_sandbox'

    for order in test_orders:
        print(f"\nTesting Order: {order['action']} {order['symbol']} {order['price_type']}")

        try:
            res = client.post('/placesmartorder', json=order)

            print(f"Status: {res.status_code}")
            print(f"Data: {res.json}")

            if res.status_code == 200:
                # Check message
                if res.json and "Rejected" in res.json.get("message", ""):
                    print("PASS: Correctly handled rejection.")
                    passed += 1
                else:
                    print("FAIL: Expected rejection message.")
                    failed += 1
            elif res.status_code in [400, 401]:
                 print(f"PASS: Mapped rejection to {res.status_code}.")
                 passed += 1
            else:
                print(f"FAIL: Unexpected status {res.status_code}")
                failed += 1

        except Exception as e:
            print(f"FAIL: Exception: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\nDiagnostic Complete. Passed: {passed}, Failed: {failed}")
    if failed == 0:
        print("Overall Result: SUCCESS")
    else:
        sys.exit(1)

if __name__ == "__main__":
    run_diagnostic()
