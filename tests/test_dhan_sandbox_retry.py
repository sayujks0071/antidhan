import sys
import unittest
from unittest.mock import MagicMock, patch
import os

# Add openalgo to sys.path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

# Mock dependencies before import
sys.modules['utils.logging'] = MagicMock()
sys.modules['database.auth_db'] = MagicMock()
sys.modules['database.token_db'] = MagicMock()
sys.modules['broker.dhan_sandbox.api.baseurl'] = MagicMock()
sys.modules['broker.dhan_sandbox.mapping.transform_data'] = MagicMock()

# Mock httpx and utils.httpx_client entirely
sys.modules['httpx'] = MagicMock()
mock_httpx_client_module = MagicMock()
sys.modules['utils.httpx_client'] = mock_httpx_client_module

# Now import the module under test
# We need to make sure we import it freshly
if 'broker.dhan_sandbox.api.order_api' in sys.modules:
    del sys.modules['broker.dhan_sandbox.api.order_api']

from broker.dhan_sandbox.api import order_api

class TestDhanSandboxRetry(unittest.TestCase):
    def setUp(self):
        # Reset mocks
        mock_httpx_client_module.reset_mock()

        # Mock the response object returned by request
        self.mock_response = MagicMock()
        self.mock_response.status_code = 200
        self.mock_response.text = '{"status": "success", "orderId": "123", "data": {}}'
        self.mock_response.json.return_value = {"status": "success", "orderId": "123", "data": {}}
        self.mock_response.headers = {}

        # Setup return values for wrapper functions
        mock_httpx_client_module.request.return_value = self.mock_response

    def test_get_api_response_uses_retry_wrapper(self):
        # Call get_api_response
        order_api.get_api_response("/test", "token", method="GET")

        # Verify utils.httpx_client.request was called with max_retries
        mock_httpx_client_module.request.assert_called_with(
            "GET",
            unittest.mock.ANY,
            headers=unittest.mock.ANY,
            content="",
            max_retries=3
        )

    def test_place_order_api_uses_retry_wrapper(self):
        data = {"symbol": "TEST", "exchange": "NSE", "apikey": "key"}
        with patch('broker.dhan_sandbox.api.order_api.transform_data', return_value={}):
            with patch('broker.dhan_sandbox.api.order_api.get_token', return_value="token"):
                 order_api.place_order_api(data, "token")

        # Verify utils.httpx_client.request was called with max_retries
        mock_httpx_client_module.request.assert_called()
        args, kwargs = mock_httpx_client_module.request.call_args
        self.assertEqual(kwargs.get('max_retries'), 3)

    def test_cancel_order_uses_retry_wrapper(self):
        order_api.cancel_order("123", "token")

        # Verify utils.httpx_client.request was called with max_retries
        mock_httpx_client_module.request.assert_called()
        args, kwargs = mock_httpx_client_module.request.call_args
        self.assertEqual(kwargs.get('max_retries'), 3)

    def test_modify_order_uses_retry_wrapper(self):
        data = {"orderid": "123", "apikey": "key"}
        with patch('broker.dhan_sandbox.api.order_api.transform_modify_order_data', return_value={}):
             order_api.modify_order(data, "token")

        # Verify utils.httpx_client.request was called with max_retries
        mock_httpx_client_module.request.assert_called()
        args, kwargs = mock_httpx_client_module.request.call_args
        self.assertEqual(kwargs.get('max_retries'), 3)

if __name__ == '__main__':
    unittest.main()
