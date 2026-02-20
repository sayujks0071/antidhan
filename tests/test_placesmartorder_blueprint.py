import unittest
import sys
import os
from unittest.mock import patch, MagicMock
from flask import Flask, session, jsonify

# Add repo root to path
sys.path.append(os.getcwd())

# Mock limiter module BEFORE importing blueprints.orders
# This prevents potential import errors or side effects from the real limiter
mock_limiter_module = MagicMock()
mock_limiter_obj = MagicMock()
# Mock the limit decorator to just return the function unmodified
mock_limiter_obj.limit = lambda x: lambda f: f
mock_limiter_module.limiter = mock_limiter_obj
sys.modules['limiter'] = mock_limiter_module

# Now import the blueprint
# We might need to mock other top-level imports if they fail
# For now, let's assume they work if we patch them during test execution
# However, if 'database.auth_db' fails at import time (e.g. connecting to DB), we might need to mock sys.modules for it too.
# Let's try importing and see.
# To be safe, let's mock the database modules too.
sys.modules['database'] = MagicMock()
sys.modules['database.auth_db'] = MagicMock()
sys.modules['database.settings_db'] = MagicMock()
sys.modules['database.token_db'] = MagicMock()
sys.modules['services'] = MagicMock()
sys.modules['services.place_smart_order_service'] = MagicMock()
sys.modules['services.close_position_service'] = MagicMock()
sys.modules['services.holdings_service'] = MagicMock()
sys.modules['services.orderbook_service'] = MagicMock()
sys.modules['services.positionbook_service'] = MagicMock()
sys.modules['services.tradebook_service'] = MagicMock()
sys.modules['services.action_center_service'] = MagicMock()
sys.modules['services.pending_order_execution_service'] = MagicMock()
sys.modules['services.cancel_all_order_service'] = MagicMock()
sys.modules['services.cancel_order_service'] = MagicMock()
sys.modules['services.modify_order_service'] = MagicMock()
sys.modules['utils'] = MagicMock()
sys.modules['utils.logging'] = MagicMock()
sys.modules['utils.session'] = MagicMock()

# Mock specific functions that are imported directly in blueprints/orders.py
# Note: blueprints/orders.py does:
# from database.auth_db import get_api_key_for_tradingview, get_auth_token
# from services.place_smart_order_service import place_smart_order
# ...
# So we need to ensure these attributes exist on the mocked modules
sys.modules['database.auth_db'].get_api_key_for_tradingview = MagicMock()
sys.modules['database.auth_db'].get_auth_token = MagicMock()
sys.modules['services.place_smart_order_service'].place_smart_order = MagicMock()
sys.modules['utils.session'].check_session_validity = lambda f: f # Identity decorator
sys.modules['utils.logging'].get_logger = MagicMock()

# Also mock get_analyze_mode and get_token (which we will add)
sys.modules['database.settings_db'].get_analyze_mode = MagicMock()
sys.modules['database.token_db'].get_token = MagicMock()


from openalgo.blueprints.orders import orders_bp

class TestPlacesmartorderBlueprint(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(orders_bp)
        self.app.secret_key = 'test_secret_key'
        self.client = self.app.test_client()

        # Reset mocks
        sys.modules['services.place_smart_order_service'].place_smart_order.reset_mock()
        sys.modules['database.token_db'].get_token.reset_mock()
        sys.modules['database.settings_db'].get_analyze_mode.reset_mock()
        sys.modules['database.auth_db'].get_auth_token.reset_mock()

    def test_placesmartorder_invalid_token(self):
        """Test that placesmartorder returns 401 if auth_token is missing (and not in analyze mode)"""
        # Setup mocks
        sys.modules['database.settings_db'].get_analyze_mode.return_value = False
        sys.modules['database.auth_db'].get_auth_token.return_value = None

        # We need a session with user
        with self.client.session_transaction() as sess:
            sess['user'] = 'testuser'
            sess['broker'] = 'dhan'

        response = self.client.post('/placesmartorder', json={
            'symbol': 'TEST', 'exchange': 'NSE'
        })

        # Verify 401 response
        self.assertEqual(response.status_code, 401)
        self.assertIn(b'Invalid Token', response.data)

        # Verify place_smart_order service was NOT called
        sys.modules['services.place_smart_order_service'].place_smart_order.assert_not_called()

    def test_placesmartorder_analyze_mode(self):
        """Test that placesmartorder proceeds if auth_token is missing BUT in analyze mode"""
        # Setup mocks
        sys.modules['database.settings_db'].get_analyze_mode.return_value = True
        sys.modules['database.auth_db'].get_auth_token.return_value = None
        sys.modules['database.auth_db'].get_api_key_for_tradingview.return_value = 'test_api_key'
        sys.modules['database.token_db'].get_token.return_value = '12345'

        # Service mock
        sys.modules['services.place_smart_order_service'].place_smart_order.return_value = (True, {'status': 'success'}, 200)

        with self.client.session_transaction() as sess:
            sess['user'] = 'testuser'
            sess['broker'] = 'dhan'

        response = self.client.post('/placesmartorder', json={
            'symbol': 'TEST', 'exchange': 'NSE'
        })

        # Verify 200 response
        self.assertEqual(response.status_code, 200)

        # Verify place_smart_order service WAS called
        sys.modules['services.place_smart_order_service'].place_smart_order.assert_called_once()

    def test_placesmartorder_security_id_required(self):
        """Test that placesmartorder returns 400 if SecurityId (token) is not found"""
        # Setup mocks
        sys.modules['database.settings_db'].get_analyze_mode.return_value = False
        sys.modules['database.auth_db'].get_auth_token.return_value = 'valid_token'
        sys.modules['database.token_db'].get_token.return_value = None # Token NOT found

        with self.client.session_transaction() as sess:
            sess['user'] = 'testuser'
            sess['broker'] = 'dhan'

        response = self.client.post('/placesmartorder', json={
            'symbol': 'INVALID_SYMBOL', 'exchange': 'NSE'
        })

        # Verify 400 response
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'SecurityId Required', response.data)

        # Verify place_smart_order service was NOT called
        sys.modules['services.place_smart_order_service'].place_smart_order.assert_not_called()

    def test_placesmartorder_valid_request(self):
        """Test a valid request calls the service"""
        # Setup mocks
        sys.modules['database.settings_db'].get_analyze_mode.return_value = False
        sys.modules['database.auth_db'].get_auth_token.return_value = 'valid_token'
        sys.modules['database.token_db'].get_token.return_value = '12345' # Valid token

        sys.modules['services.place_smart_order_service'].place_smart_order.return_value = (True, {'status': 'success', 'orderid': '1001'}, 200)

        with self.client.session_transaction() as sess:
            sess['user'] = 'testuser'
            sess['broker'] = 'dhan'

        response = self.client.post('/placesmartorder', json={
            'symbol': 'TEST', 'exchange': 'NSE'
        })

        # Verify 200 response
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'1001', response.data)

        # Verify place_smart_order service WAS called
        sys.modules['services.place_smart_order_service'].place_smart_order.assert_called_once()

if __name__ == '__main__':
    unittest.main()
