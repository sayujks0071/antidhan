import unittest
from unittest.mock import patch
import os
import sys

# Add openalgo root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
openalgo_root = os.path.join(project_root, 'openalgo')

sys.path.insert(0, project_root)
sys.path.insert(0, openalgo_root)

# Remove mocked modules if they exist to avoid confusion
for mod in ['utils', 'utils.env_check', 'utils.logging']:
    if mod in sys.modules:
        del sys.modules[mod]

# Patch environment variable check in auth_db before it gets imported
os.environ['API_KEY_PEPPER'] = 'a' * 64
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

class OrderFlowSimulation(unittest.TestCase):
    def setUp(self):
        """Set up the test client and mock dependencies."""
        from flask import Flask

        try:
            from openalgo.blueprints.orders import orders_bp
        except Exception as e:
            print(f"Error importing blueprint: {e}")
            raise

        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        self.app.register_blueprint(orders_bp)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

        # We need to use app_context or request_context when patching session
        # But patching session is tricky because it's a proxy.
        # Instead of patching session, we can push a context and modify session directly?
        # Or patch it where it is used.
        # The error "Working outside of request context" usually happens when accessing session/g/request
        # outside of a request. But patching typically replaces the proxy object itself.
        # The issue might be that the patch target 'openalgo.blueprints.orders.session'
        # is a werkzeug.local.LocalProxy which behaves weirdly when patched.

        # Alternative: Don't patch session directly.
        # The blueprint uses: login_username = session["user"]
        # We can use client.session_transaction() to set session variables.

        # Mock get_auth_token
        self.auth_patch = patch('openalgo.blueprints.orders.get_auth_token')
        self.mock_auth = self.auth_patch.start()
        self.mock_auth.return_value = 'mock_token'

        # Mock get_api_key_for_tradingview
        self.api_key_patch = patch('openalgo.database.auth_db.get_api_key_for_tradingview')
        self.mock_api_key = self.api_key_patch.start()
        self.mock_api_key.return_value = 'mock_api_key'

        # Mock get_token (SecurityId check)
        self.token_patch = patch('openalgo.services.place_smart_order_service.get_token')
        self.mock_token = self.token_patch.start()
        self.mock_token.return_value = '12345'

        # Mock place_smart_order_service
        self.service_patch = patch('openalgo.services.place_smart_order_service.place_smart_order')
        self.mock_service = self.service_patch.start()

        # Mock database functions used in orders.py
        self.analyze_mode_patch = patch('openalgo.blueprints.orders.get_analyze_mode')
        self.mock_analyze = self.analyze_mode_patch.start()
        self.mock_analyze.return_value = False

    def tearDown(self):
        self.auth_patch.stop()
        self.api_key_patch.stop()
        self.token_patch.stop()
        self.service_patch.stop()
        self.analyze_mode_patch.stop()

    def test_market_order_rejection(self):
        """Test MARKET order handling when rejected."""
        self.mock_service.return_value = (False, {"status": "error", "message": "REJECTED: Market Closed"}, 200)

        payload = {
            "symbol": "CRUDEOIL",
            "exchange": "MCX",
            "action": "BUY",
            "product": "NRML",
            "pricetype": "MARKET",
            "quantity": "1"
        }

        with self.client.session_transaction() as sess:
            sess['user'] = 'test_user'
            sess['broker'] = 'Dhan Sandbox'

        response = self.client.post('/placesmartorder', json=payload)
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'error')
        self.assertIn('REJECTED', data['message'])
        print(f"\n[MARKET] Response: {data}")

    def test_limit_order_success(self):
        """Test LIMIT order handling when successful."""
        self.mock_service.return_value = (True, {"status": "success", "orderid": "1001"}, 200)

        payload = {
            "symbol": "CRUDEOIL",
            "exchange": "MCX",
            "action": "BUY",
            "product": "NRML",
            "pricetype": "LIMIT",
            "price": "6000",
            "quantity": "1"
        }

        with self.client.session_transaction() as sess:
            sess['user'] = 'test_user'
            sess['broker'] = 'Dhan Sandbox'

        response = self.client.post('/placesmartorder', json=payload)
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['orderid'], '1001')
        print(f"\n[LIMIT] Response: {data}")

    def test_sl_order(self):
        """Test SL order flow."""
        self.mock_service.return_value = (True, {"status": "success", "orderid": "1002"}, 200)

        payload = {
            "symbol": "CRUDEOIL",
            "exchange": "MCX",
            "action": "SELL",
            "product": "NRML",
            "pricetype": "SL",
            "price": "5900",
            "trigger_price": "5910",
            "quantity": "1"
        }

        with self.client.session_transaction() as sess:
            sess['user'] = 'test_user'
            sess['broker'] = 'Dhan Sandbox'

        response = self.client.post('/placesmartorder', json=payload)
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        print(f"\n[SL] Response: {data}")

    def test_slm_order(self):
        """Test SL-M order flow."""
        self.mock_service.return_value = (True, {"status": "success", "orderid": "1003"}, 200)

        payload = {
            "symbol": "CRUDEOIL",
            "exchange": "MCX",
            "action": "SELL",
            "product": "NRML",
            "pricetype": "SL-M",
            "trigger_price": "5910",
            "quantity": "1"
        }

        with self.client.session_transaction() as sess:
            sess['user'] = 'test_user'
            sess['broker'] = 'Dhan Sandbox'

        response = self.client.post('/placesmartorder', json=payload)
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        print(f"\n[SL-M] Response: {data}")

    def test_bracket_order(self):
        """Test Bracket order flow (simulated parameters)."""
        self.mock_service.return_value = (True, {"status": "success", "orderid": "1004"}, 200)

        payload = {
            "symbol": "CRUDEOIL",
            "exchange": "MCX",
            "action": "BUY",
            "product": "MIS", # BO usually requires MIS/Intraday
            "pricetype": "LIMIT",
            "price": "6000",
            "quantity": "1",
            "bo_profit_value": "10",
            "bo_stop_loss_value": "5"
        }

        with self.client.session_transaction() as sess:
            sess['user'] = 'test_user'
            sess['broker'] = 'Dhan Sandbox'

        response = self.client.post('/placesmartorder', json=payload)
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        print(f"\n[BRACKET] Response: {data}")

    def test_invalid_token_error(self):
        """Test handling of 401 Invalid Token from service."""
        # Note: blueprints/orders.py catches 401 and returns 401 JSON
        self.mock_service.return_value = (False, {"status": "error", "message": "Invalid Token"}, 401)

        payload = {"symbol": "INVALID", "exchange": "NSE"}

        with self.client.session_transaction() as sess:
            sess['user'] = 'test_user'
            sess['broker'] = 'Dhan Sandbox'

        response = self.client.post('/placesmartorder', json=payload)
        data = response.get_json()

        self.assertEqual(response.status_code, 401)
        self.assertEqual(data['message'], "Invalid Token")
        print(f"\n[401 ERROR] Response: {data}")

if __name__ == '__main__':
    unittest.main()
