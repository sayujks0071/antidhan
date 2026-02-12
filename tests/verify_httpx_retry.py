import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Mock httpx before import
mock_httpx = MagicMock()
sys.modules['httpx'] = mock_httpx

# Mock classes needed
class MockResponse:
    def __init__(self, status_code, headers=None, request=None, text="{}", http_version="HTTP/1.1"):
        self.status_code = status_code
        self.headers = headers or {}
        self.request = request
        self.text = text
        self.http_version = http_version

class MockRequest:
    def __init__(self, method, url):
        self.method = method
        self.url = url
        self.extensions = {}

mock_httpx.Response = MockResponse
mock_httpx.Request = MockRequest
mock_httpx.Limits = MagicMock()
mock_httpx.HTTPError = Exception
mock_httpx.RequestError = Exception
mock_httpx.TimeoutException = Exception

# Add openalgo to path so we can import utils
# We need absolute path to openalgo/
current_dir = os.path.dirname(os.path.abspath(__file__))
# tests/ -> openalgo/
openalgo_path = os.path.abspath(os.path.join(current_dir, '../openalgo'))
sys.path.insert(0, openalgo_path)

# Mock utils.logging specifically
sys.modules['utils.logging'] = MagicMock()
sys.modules['utils.logging'].get_logger.return_value = MagicMock()

# Now we can import utils.httpx_client
# It will import httpx (mocked) and utils.logging (mocked)
try:
    from utils.httpx_client import request, get_httpx_client
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)


class TestHttpxRetry(unittest.TestCase):
    def setUp(self):
        # Reset the global client
        import utils.httpx_client
        utils.httpx_client._httpx_client = None

    @patch('utils.httpx_client.get_httpx_client')
    @patch('time.sleep')
    def test_retry_on_500(self, mock_sleep, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Setup response sequence: 500, 500, 200
        # First call: 500 -> retry 1
        # Second call: 500 -> retry 2
        # Third call: 200 -> success

        response_500 = MockResponse(500, request=MockRequest("GET", "http://test.com"))
        response_200 = MockResponse(200, request=MockRequest("GET", "http://test.com"))

        mock_client.request.side_effect = [response_500, response_500, response_200]

        response = request("GET", "http://test.com", max_retries=3, backoff_factor=0.1)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_client.request.call_count, 3)
        # Verify sleep was called twice
        self.assertEqual(mock_sleep.call_count, 2)

    @patch('utils.httpx_client.get_httpx_client')
    @patch('time.sleep')
    def test_retry_after_header(self, mock_sleep, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Setup response: 429 with Retry-After: 2
        headers = {'Retry-After': '2'}
        response_429 = MockResponse(429, headers=headers, request=MockRequest("GET", "http://test.com"))
        response_200 = MockResponse(200, request=MockRequest("GET", "http://test.com"))

        mock_client.request.side_effect = [response_429, response_200]

        response = request("GET", "http://test.com", max_retries=3)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_client.request.call_count, 2)

        # Verify sleep called with at least 2 seconds (Retry-After)
        args_list = mock_sleep.call_args_list
        self.assertEqual(len(args_list), 1)
        # Check first argument of the first call
        self.assertGreaterEqual(float(args_list[0][0][0]), 2.0)

if __name__ == '__main__':
    unittest.main()
