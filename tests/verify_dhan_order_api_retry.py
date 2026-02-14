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
sys.modules['broker.dhan.api.baseurl'] = MagicMock()
sys.modules['broker.dhan.mapping.transform_data'] = MagicMock()

# Mock httpx and utils.httpx_client entirely
sys.modules['httpx'] = MagicMock()
mock_httpx_client_module = MagicMock()
sys.modules['utils.httpx_client'] = mock_httpx_client_module

# Now import the module under test
# We need to make sure we import it freshly if it was already imported (it shouldn't be in this process)
if 'broker.dhan.api.order_api' in sys.modules:
    del sys.modules['broker.dhan.api.order_api']

from broker.dhan.api import order_api

class TestDhanOrderApiRetry(unittest.TestCase):
    def setUp(self):
        # Reset mocks
        mock_httpx_client_module.reset_mock()

        # Mock the response object returned by get/post/etc
        self.mock_response = MagicMock()
        self.mock_response.status_code = 200
        self.mock_response.text = '{"status": "success", "orderId": "123", "data": {}}'
        self.mock_response.json.return_value = {"status": "success", "orderId": "123", "data": {}}
        self.mock_response.headers = {}

        # Setup return values for wrapper functions
        mock_httpx_client_module.get.return_value = self.mock_response
        mock_httpx_client_module.post.return_value = self.mock_response
        mock_httpx_client_module.put.return_value = self.mock_response
        mock_httpx_client_module.delete.return_value = self.mock_response
        mock_httpx_client_module.request.return_value = self.mock_response

        # Setup return value for get_httpx_client() to ensure old way is NOT used or mocked correctly if needed
        # We want to ensure the module level functions are used.
        self.mock_client = MagicMock()
        mock_httpx_client_module.get_httpx_client.return_value = self.mock_client

    def test_get_api_response_uses_wrapper(self):
        # Call get_api_response with GET
        order_api.get_api_response("/test", "token", method="GET")

        # Verify utils.httpx_client.get was called
        # If it uses client.get(), this assertion will fail, which is what we want (it proves we switched to wrapper)
        mock_httpx_client_module.get.assert_called()

    def test_place_order_api_uses_wrapper(self):
        data = {"symbol": "TEST", "exchange": "NSE", "apikey": "key"}
        with patch.dict(os.environ, {"BROKER_API_KEY": "test_broker_key"}):
            with patch('broker.dhan.api.order_api.transform_data', return_value={}):
                with patch('broker.dhan.api.order_api.get_token', return_value="token"):
                # verification of verify_api_key might be needed if mocked strictly
                    with patch('broker.dhan.api.order_api.verify_api_key', return_value="user_id"):
                        with patch('broker.dhan.api.order_api.get_user_id', return_value="client_id"):
                            order_api.place_order_api(data, "token")

        # Verify utils.httpx_client.post was called
        mock_httpx_client_module.post.assert_called()

    def test_cancel_order_uses_wrapper(self):
        order_api.cancel_order("123", "token")

        # Verify utils.httpx_client.delete was called
        mock_httpx_client_module.delete.assert_called()

    def test_modify_order_uses_wrapper(self):
        data = {"orderid": "123", "apikey": "key"}
        with patch('broker.dhan.api.order_api.transform_modify_order_data', return_value={}):
             order_api.modify_order(data, "token")

        # Verify utils.httpx_client.put was called
        mock_httpx_client_module.put.assert_called()

if __name__ == '__main__':
    unittest.main()
