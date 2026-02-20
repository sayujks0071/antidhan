#!/usr/bin/env python3
import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import json

# Add repo root to path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Set dummy env vars for Flask App
os.environ['DATABASE_URL'] = "sqlite:///:memory:"
os.environ['APP_KEY'] = "test_key_at_least_32_chars_long_12345"
os.environ['BROKER_API_KEY'] = "test_broker_key"
os.environ['API_KEY_PEPPER'] = "test_pepper_12345_test_pepper_12345"
os.environ['FLASK_TESTING'] = "True"
os.environ['CSRF_ENABLED'] = "False" # Disable CSRF for testing

# Pre-mock heavy dependencies to avoid issues/timeouts
sys.modules['openalgo.api'] = MagicMock()
sys.modules['services.telegram_bot_service'] = MagicMock()
sys.modules['openalgo.services.telegram_bot_service'] = MagicMock()
sys.modules['services.flow_scheduler_service'] = MagicMock()
sys.modules['services.historify_scheduler_service'] = MagicMock()
sys.modules['websocket_proxy.app_integration'] = MagicMock()

# Import openalgo and inject 'api' if missing
try:
    import openalgo
    if not hasattr(openalgo, 'api'):
        openalgo.api = MagicMock()
except ImportError:
    pass

# Import create_app
try:
    from openalgo.app import create_app
except ImportError:
    sys.path.insert(0, os.path.join(repo_root, "openalgo"))
    import openalgo
    if not hasattr(openalgo, 'api'):
        openalgo.api = MagicMock()
    from openalgo.app import create_app

class TestOrderFlowBlueprint(unittest.TestCase):
    def setUp(self):
        # Create app
        self.app = create_app()
        self.app.config['WTF_CSRF_ENABLED'] = False # Force disable CSRF
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    # Patch top-level modules because app.py imports them directly
    @patch('blueprints.orders.place_smart_order')
    @patch('blueprints.orders.get_auth_token')
    @patch('database.auth_db.get_api_key_for_tradingview') # Imported inside function
    @patch('utils.session.is_session_valid')
    def test_placesmartorder_rejection(self, mock_is_valid, mock_get_api_key, mock_get_auth_token, mock_place_smart_order):
        print("\n--- Diagnostic Order Flow v4: Testing Blueprint Rejection Handling ---")

        # Mock Session Validity
        mock_is_valid.return_value = True

        # Mock Auth Token and API Key
        mock_get_auth_token.return_value = "mock_token"
        mock_get_api_key.return_value = "mock_api_key"

        # Mock place_smart_order to return Rejection
        # Note: blueprint expects (success, response_data, status_code)
        error_response = {
            "status": "error",
            "message": "Order Rejected: Market is Closed",
            "data": {"orderStatus": "REJECTED"}
        }

        mock_place_smart_order.return_value = (False, error_response, 200)

        order_types = ["LIMIT", "MARKET", "SL", "SL-M", "BRACKET"]

        for o_type in order_types:
            print(f"Testing Order Type: {o_type}")

            payload = {
                "strategy": "DiagnosticTest", # Mandatory
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "action": "BUY",
                "quantity": "1",
                "pricetype": o_type,
                "product": "MIS",
                "price": "100" if o_type != "MARKET" else "0",
                "trigger_price": "99" if "SL" in o_type else "0",
                "position_size": "1"
            }

            with self.client.session_transaction() as sess:
                sess['user'] = 'test_user'
                sess['broker'] = 'dhan_sandbox'
                sess['logged_in'] = True

            response = self.client.post('/placesmartorder', json=payload)

            print(f"  Response Status: {response.status_code}")
            print(f"  Response Body: {response.json}")

            # Assertions
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['status'], 'error')
            self.assertIn("Market is Closed", response.json['message'])
            print("  PASS")

if __name__ == "__main__":
    unittest.main()
