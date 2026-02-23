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
sys.modules['database.apilog_db'] = MagicMock()
sys.modules['broker.dhan_sandbox.api.baseurl'] = MagicMock()
sys.modules['broker.dhan_sandbox.mapping.transform_data'] = MagicMock()

# Mock httpx and utils.httpx_client entirely
sys.modules['httpx'] = MagicMock()
mock_httpx_client_module = MagicMock()
sys.modules['utils.httpx_client'] = mock_httpx_client_module

# Now import the module under test
# We need to make sure we import it freshly if it was already imported
if 'broker.dhan_sandbox.api.order_api' in sys.modules:
    del sys.modules['broker.dhan_sandbox.api.order_api']

from broker.dhan_sandbox.api import order_api

class TestDhanSandboxOrderApiRetry(unittest.TestCase):
    def setUp(self):
        # Reset mocks
        mock_httpx_client_module.reset_mock()

        # Mock the response object returned by get/post/etc
        self.mock_response = MagicMock()
        self.mock_response.status_code = 200
        self.mock_response.text = '{"status": "success", "orderId": "123", "data": {}}'
        self.mock_response.json.return_value = {"status": "success", "orderId": "123", "data": {}}
        self.mock_response.headers = {}
        # Make sure it has .status attribute as code assigns it
        self.mock_response.status = 200

        # Setup return values for wrapper functions
        mock_httpx_client_module.get.return_value = self.mock_response
        mock_httpx_client_module.post.return_value = self.mock_response
        mock_httpx_client_module.put.return_value = self.mock_response
        mock_httpx_client_module.delete.return_value = self.mock_response
        mock_httpx_client_module.request.return_value = self.mock_response

        # Setup return value for get_httpx_client() to ensure old way is NOT used or mocked correctly if needed
        self.mock_client = MagicMock()
        mock_httpx_client_module.get_httpx_client.return_value = self.mock_client

    def test_get_api_response_uses_wrapper(self):
        """Verify get_api_response uses request wrapper with retries"""
        # Call get_api_response with GET
        order_api.get_api_response("/test", "token", method="GET")

        # Verify utils.httpx_client.request was called
        mock_httpx_client_module.request.assert_called()

        # Verify call arguments
        args, kwargs = mock_httpx_client_module.request.call_args
        self.assertEqual(args[0], "GET")
        self.assertEqual(kwargs.get('max_retries'), 3)

    def test_place_order_api_uses_wrapper(self):
        """Verify place_order_api uses request wrapper with retries"""
        data = {"symbol": "TEST", "exchange": "NSE", "apikey": "key", "action": "BUY", "quantity": "1", "pricetype": "MARKET", "product": "MIS"}

        # Patch dependencies needed for place_order_api
        with patch.dict(os.environ, {"BROKER_API_KEY": "test_broker_key"}):
            with patch('broker.dhan_sandbox.api.order_api.transform_data', return_value={}):
                with patch('broker.dhan_sandbox.api.order_api.get_token', return_value="token"):
                    # Call the function
                    order_api.place_order_api(data, "token")

        # Verify utils.httpx_client.request was called with POST
        mock_httpx_client_module.request.assert_called()
        args, kwargs = mock_httpx_client_module.request.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(kwargs.get('max_retries'), 3)

    def test_cancel_order_uses_wrapper(self):
        """Verify cancel_order uses request wrapper with retries"""
        order_api.cancel_order("123", "token")

        # Verify utils.httpx_client.request was called with DELETE
        mock_httpx_client_module.request.assert_called()
        args, kwargs = mock_httpx_client_module.request.call_args
        self.assertEqual(args[0], "DELETE")
        self.assertEqual(kwargs.get('max_retries'), 3)

    def test_modify_order_uses_wrapper(self):
        """Verify modify_order uses request wrapper with retries"""
        data = {"orderid": "123", "apikey": "key"}
        with patch('broker.dhan_sandbox.api.order_api.transform_modify_order_data', return_value={}):
             order_api.modify_order(data, "token")

        # Verify utils.httpx_client.request was called with PUT
        mock_httpx_client_module.request.assert_called()
        args, kwargs = mock_httpx_client_module.request.call_args
        self.assertEqual(args[0], "PUT")
        self.assertEqual(kwargs.get('max_retries'), 3)

if __name__ == '__main__':
    unittest.main()
