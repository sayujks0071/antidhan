import sys
import os
import unittest
import time
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
class RequestError(Exception): pass
class TimeoutException(RequestError): pass
mock_httpx.RequestError = RequestError
mock_httpx.TimeoutException = TimeoutException

# Add openalgo to path so we can import utils
current_dir = os.path.dirname(os.path.abspath(__file__))
openalgo_path = os.path.abspath(os.path.join(current_dir, '../openalgo'))
sys.path.insert(0, openalgo_path)

# Mock utils.logging specifically
sys.modules['utils.logging'] = MagicMock()
sys.modules['utils.logging'].get_logger.return_value = MagicMock()

# Now import utils.httpx_client
try:
    from utils.httpx_client import request, get_httpx_client
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)

class TestHttpxTimeoutRetry(unittest.TestCase):
    def setUp(self):
        # Reset the global client
        import utils.httpx_client
        utils.httpx_client._httpx_client = None

    @patch('utils.httpx_client.get_httpx_client')
    @patch('time.sleep')
    def test_retry_on_timeout(self, mock_sleep, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Setup side effect: Timeout, Timeout, Success
        response_200 = MockResponse(200, request=MockRequest("GET", "http://test.com"))

        # side_effect can take an exception class or instance
        mock_client.request.side_effect = [TimeoutException("Timeout"), TimeoutException("Timeout"), response_200]

        print("Testing retry on TimeoutException...")
        response = request("GET", "http://test.com", max_retries=3, backoff_factor=0.01)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_client.request.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)
        print("SUCCESS: Retried 3 times on Timeout.")

        with open("DAILY_PERFORMANCE.md", "a") as f:
            f.write("\n## Error Handling\n")
            f.write("- **Scenario**: `httpx.TimeoutException`\n")
            f.write("- **Result**: PASSED. `Retry-with-Backoff` correctly handles timeouts (Retried 2 times before success).\n")

if __name__ == '__main__':
    unittest.main()
