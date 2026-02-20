import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from functools import wraps
from flask import Flask, session, json

# Add openalgo to sys.path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

# Set dummy env vars
os.environ['API_KEY_PEPPER'] = '12345678901234567890123456789012'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

# Setup Mocks for dependencies of orders_bp and place_smart_order_service
sys.modules['limiter'] = MagicMock()
sys.modules['limiter'].limiter = MagicMock()
sys.modules['limiter'].limiter.limit = lambda x: lambda f: f

# Mock database modules
sys.modules['database.analyzer_db'] = MagicMock()
sys.modules['database.apilog_db'] = MagicMock()
sys.modules['database.telegram_db'] = MagicMock()
sys.modules['database.action_center_db'] = MagicMock()
sys.modules['database.auth_db'] = MagicMock()
sys.modules['database.settings_db'] = MagicMock()
sys.modules['services.action_center_service'] = MagicMock()
sys.modules['services.pending_order_execution_service'] = MagicMock()

# Mock other modules
sys.modules['extensions'] = MagicMock()
sys.modules['services.telegram_alert_service'] = MagicMock()
sys.modules['utils.api_analyzer'] = MagicMock()

# Mock session validity check
def dummy_decorator(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function

sys.modules['utils.session'] = MagicMock()
sys.modules['utils.session'].check_session_validity = dummy_decorator

# Import blueprint after mocks
try:
    from blueprints.orders import orders_bp
except ImportError as e:
    print(f"ImportError during setup: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

app = Flask(__name__)
app.secret_key = 'test_secret'
app.register_blueprint(orders_bp)

class TestOrderFlow(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    @patch('blueprints.orders.get_auth_token')
    @patch('blueprints.orders.get_api_key_for_tradingview')
    @patch('blueprints.orders.get_analyze_mode')
    @patch('services.place_smart_order_service.import_broker_module')
    @patch('services.place_smart_order_service.get_token')
    @patch('services.place_smart_order_service.get_analyze_mode')
    def test_order_types(self, mock_service_analyze, mock_get_token, mock_import_broker,
                         mock_bp_analyze, mock_bp_apikey, mock_bp_token):

        # Setup Common Mocks
        mock_bp_token.return_value = "dummy_token"
        mock_bp_apikey.return_value = "dummy_api_key"
        mock_bp_analyze.return_value = False # Live Mode
        mock_service_analyze.return_value = False # Live Mode
        mock_get_token.return_value = "12345" # Valid Token

        # Mock Broker
        mock_broker = MagicMock()
        mock_import_broker.return_value = mock_broker

        # Simulate "Market Closed" / Rejection
        # place_smartorder_api returns (response_obj, response_dict, order_id)
        # For rejection: order_id is None, response_dict has message
        mock_res = MagicMock()
        mock_res.status = 200 # API returns 200 OK even for rejection often
        mock_broker.place_smartorder_api.return_value = (
            mock_res,
            {"status": "success", "message": "Order Rejected: Market Closed", "orderStatus": "REJECTED"},
            None # Order ID is None
        )

        order_types = [
            ("LIMIT", "MIS"),
            ("MARKET", "MIS"),
            ("SL", "MIS"),
            ("SL-M", "MIS"),
            ("BRACKET", "MIS")
        ]

        with self.client.session_transaction() as sess:
            sess['user'] = 'test_user'
            sess['broker'] = 'dhan_sandbox'

        for price_type, product in order_types:
            print(f"\nTesting Order Type: {price_type}, Product: {product}")

            payload = {
                "symbol": "SBIN",
                "exchange": "NSE",
                "action": "BUY",
                "quantity": 1,
                "pricetype": price_type,
                "product": product,
                "price": 100,
                "trigger_price": 99,
                "strategy": "DIAGNOSTIC",
                "position_size": 1
            }

            res = self.client.post('/placesmartorder', json=payload)

            print(f"Status Code: {res.status_code}")
            print(f"Response: {res.json}")

            if price_type == "BRACKET":
                # BRACKET is not in VALID_PRICE_TYPES, so it should be rejected 400 by validate_smart_order
                if res.status_code == 400:
                     print("SUCCESS: BRACKET correctly rejected by validation (400).")
                else:
                     print(f"WARNING: BRACKET got {res.status_code}, expected 400.")
            else:
                # Valid price types but rejected by broker
                if res.status_code == 200:
                    data = res.json
                    if data['status'] == 'error' and "Rejected" in data['message']:
                         print("SUCCESS: Order correctly handled as Rejected (200 OK with error status).")
                    else:
                         print(f"FAILURE: Unexpected response content: {data}")
                else:
                     print(f"FAILURE: Unexpected status code {res.status_code}")

if __name__ == '__main__':
    unittest.main()
