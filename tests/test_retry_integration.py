import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add openalgo directory to path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

# Mock dependencies we don't care about
sys.modules['database.auth_db'] = MagicMock()
sys.modules['database.token_db'] = MagicMock()
sys.modules['database.apilog_db'] = MagicMock()
sys.modules['database.settings_db'] = MagicMock()
sys.modules['utils.logging'] = MagicMock()
sys.modules['utils.session'] = MagicMock()
sys.modules['utils.api_analyzer'] = MagicMock()
sys.modules['services.telegram_alert_service'] = MagicMock()
sys.modules['extensions'] = MagicMock()
sys.modules['database.analyzer_db'] = MagicMock()
sys.modules['services.order_router_service'] = MagicMock()
sys.modules['services.order_router_service'].should_route_to_pending.return_value = False

# Mock specific functions
sys.modules['database.auth_db'].get_auth_token_broker = MagicMock(return_value=("fake_token", "dhan_sandbox"))
sys.modules['database.token_db'].get_token = MagicMock(return_value="fake_security_id")
sys.modules['database.settings_db'].get_analyze_mode = MagicMock(return_value=False)

# Mock utils.httpx_client before importing broker module
mock_httpx_client = MagicMock()
sys.modules['utils.httpx_client'] = mock_httpx_client

# We want to test broker.dhan_sandbox.api.order_api using utils.httpx_client.request
# But wait! request itself implements retry logic.
# If we mock request, we just verify it was called.
# We want to verify that *if request fails* (simulated), retry happens?
# No, request *implements* retry.
# If we mock request, we replace the retry logic with a mock.
# We should import the REAL request function and mock the underlying httpx client used by it.

# Let's import the REAL utils.httpx_client first
# But wait, utils.httpx_client imports httpx.
# We can mock httpx.Client inside utils.httpx_client.

# Clear previous mocks of utils.httpx_client if any
if 'utils.httpx_client' in sys.modules:
    del sys.modules['utils.httpx_client']

# Import the real module
from utils import httpx_client

# Now patch get_httpx_client to return a mock client
mock_client_instance = MagicMock()
httpx_client.get_httpx_client = MagicMock(return_value=mock_client_instance)

# Now import the broker module so it uses the real request function (which uses our mock client)
from broker.dhan_sandbox.api import order_api

# Now import the service
from services.place_smart_order_service import place_smart_order

class TestFullRetryFlow(unittest.TestCase):
    def setUp(self):
        # Reset mock client
        mock_client_instance.reset_mock()

        # Configure mock client to simulate failure then success
        # We need to simulate the response object structure expected by request()
        self.response_500 = MagicMock()
        self.response_500.status_code = 500
        self.response_500.text = "Internal Server Error"

        self.response_200 = MagicMock()
        self.response_200.status_code = 200
        self.response_200.text = '{"status": "success", "orderId": "12345"}'
        self.response_200.json.return_value = {"status": "success", "orderId": "12345"}

        # Simulate place_order_api call
        # It calls request("POST", ...)
        # request calls client.request(...)

    def test_retry_mechanism_active(self):
        """Verify that place_smart_order triggers retries when broker returns 500"""

        # Setup the mock client to fail twice with 500, then succeed
        mock_client_instance.request.side_effect = [self.response_500, self.response_500, self.response_200]

        # Order data
        order_data = {
            "symbol": "TEST",
            "exchange": "NSE",
            "action": "BUY",
            "quantity": "1",
            "price_type": "MARKET",
            "pricetype": "MARKET",
            "product_type": "MIS",
            "product": "MIS",
            "apikey": "test_api_key",
            "strategy": "TEST_STRATEGY",
            "position_size": "1"
        }

        # Call place_smart_order
        # It calls place_smart_order_with_auth -> broker.dhan_sandbox.api.order_api.place_smartorder_api
        # -> place_order_api -> request -> client.request

        # We need to ensure get_token is mocked correctly for order_api
        with patch('database.token_db.get_token', return_value="12345"):
             # Also need to mock get_open_position inside order_api to avoid that call failing
             # But wait, place_smartorder_api calls get_open_position first.
             # We should mock get_open_position to succeed so we reach place_order_api.
             with patch('broker.dhan_sandbox.api.order_api.get_open_position', return_value="0"):
                  success, response, status_code = place_smart_order(
                      order_data=order_data,
                      api_key="test_api_key"
                  )

        # Debug
        print(f"Success: {success}, Status Code: {status_code}, Response: {response}")

        # Verify result
        self.assertTrue(success)
        self.assertEqual(status_code, 200)
        self.assertEqual(response.get("orderid"), "12345")

        # Verify retries happened
        # client.request should have been called 3 times (500, 500, 200)
        self.assertEqual(mock_client_instance.request.call_count, 3)

if __name__ == '__main__':
    unittest.main()
