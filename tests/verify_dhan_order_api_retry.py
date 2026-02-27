import sys
import unittest
from unittest.mock import MagicMock, patch
import os

# Add openalgo to sys.path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

# Create mocks for dependencies
mock_utils_logging = MagicMock()
mock_auth_db = MagicMock()
mock_token_db = MagicMock()
mock_apilog_db = MagicMock()
mock_baseurl = MagicMock()
mock_transform_data = MagicMock()
mock_httpx = MagicMock()

# Create a mock for utils.httpx_client that will replace the actual module
mock_utils_httpx_client = MagicMock()

# Set up the mock for the 'request' function specifically
# This is crucial because `from utils.httpx_client import request` imports the function object
mock_request_func = MagicMock()
mock_utils_httpx_client.request = mock_request_func
# Also mock get_httpx_client just in case
mock_utils_httpx_client.get_httpx_client = MagicMock()

# Patch sys.modules with our mocks BEFORE importing the module under test
# This ensures that `from utils.httpx_client import request` gets our mock function
with patch.dict(sys.modules, {
    'utils.logging': mock_utils_logging,
    'database.auth_db': mock_auth_db,
    'database.token_db': mock_token_db,
    'database.apilog_db': mock_apilog_db,
    'broker.dhan_sandbox.api.baseurl': mock_baseurl,
    'broker.dhan_sandbox.mapping.transform_data': mock_transform_data,
    'httpx': mock_httpx,
    'utils.httpx_client': mock_utils_httpx_client
}):
    # Import the module under test inside the patch context
    # This forces it to use our mocked modules
    # Note: We must ensure it's reloaded if it was already imported
    if 'broker.dhan_sandbox.api.order_api' in sys.modules:
        del sys.modules['broker.dhan_sandbox.api.order_api']

    from broker.dhan_sandbox.api import order_api

class TestDhanOrderApiRetry(unittest.TestCase):
    def setUp(self):
        # Reset the mock for the request function before each test
        mock_request_func.reset_mock()

        # Mock the response object returned by the request function
        self.mock_response = MagicMock()
        self.mock_response.status_code = 200
        self.mock_response.text = '{"status": "success", "orderId": "123", "data": {}}'
        self.mock_response.json.return_value = {"status": "success", "orderId": "123", "data": {}}
        self.mock_response.headers = {}

        # Set the mock request function to return our mock response
        mock_request_func.return_value = self.mock_response

    def test_get_api_response_uses_wrapper(self):
        # Call get_api_response with GET
        order_api.get_api_response("/test", "token", method="GET")

        # Verify utils.httpx_client.request was called with retry logic
        mock_request_func.assert_called()
        args, kwargs = mock_request_func.call_args
        self.assertEqual(kwargs.get('max_retries'), 3)
        # Verify it was called with GET
        self.assertEqual(args[0], "GET")

    def test_place_order_api_uses_wrapper(self):
        data = {"symbol": "TEST", "exchange": "NSE", "apikey": "key"}

        # We need to mock functions imported inside the module or used by it
        with patch.dict(os.environ, {"BROKER_API_KEY": "test_broker_key"}):
            # The module uses these imported functions, so we mock them on the imported module
            order_api.transform_data = MagicMock(return_value={})
            order_api.get_token = MagicMock(return_value="token")

            # Place the order
            order_api.place_order_api(data, "token")

        # Verify utils.httpx_client.request was called with retry logic
        mock_request_func.assert_called()
        args, kwargs = mock_request_func.call_args
        self.assertEqual(kwargs.get('max_retries'), 3)
        self.assertEqual(args[0], "POST")

    def test_cancel_order_uses_wrapper(self):
        order_api.cancel_order("123", "token")

        # Verify utils.httpx_client.request was called with retry logic
        mock_request_func.assert_called()
        args, kwargs = mock_request_func.call_args
        self.assertEqual(kwargs.get('max_retries'), 3)
        self.assertEqual(args[0], "DELETE")

    def test_modify_order_uses_wrapper(self):
        data = {"orderid": "123", "apikey": "key"}
        order_api.transform_modify_order_data = MagicMock(return_value={})

        order_api.modify_order(data, "token")

        # Verify utils.httpx_client.request was called with retry logic
        mock_request_func.assert_called()
        args, kwargs = mock_request_func.call_args
        self.assertEqual(kwargs.get('max_retries'), 3)
        self.assertEqual(args[0], "PUT")

if __name__ == '__main__':
    unittest.main()
