import unittest
from unittest.mock import patch, Mock
import httpx
import sys
import os

# Add openalgo to sys.path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

from utils.httpx_client import request, cleanup_httpx_client

class TestHttpxTimeoutRetry(unittest.TestCase):
    def setUp(self):
        cleanup_httpx_client()

    def tearDown(self):
        cleanup_httpx_client()

    @patch('utils.httpx_client.time.sleep')
    @patch('httpx.Client.request')
    def test_retry_on_timeout_exception(self, mock_request, mock_sleep):
        # Setup mock to raise TimeoutException twice, then succeed
        # Note: TimeoutException requires a message in some versions, or request/response args
        # We'll just instantiate it simply if possible, or mock it

        # httpx.TimeoutException(message, request=...)
        # But for testing we can just raise it
        timeout_exc = httpx.TimeoutException("Read timed out")

        mock_request.side_effect = [
            timeout_exc,
            timeout_exc,
            httpx.Response(200, request=httpx.Request("GET", "http://test.com"))
        ]

        # Call request with retries
        response = request("GET", "http://test.com", max_retries=3, backoff_factor=0.1)

        # Verify result
        self.assertEqual(response.status_code, 200)

        # Verify retries
        self.assertEqual(mock_request.call_count, 3)

        # Verify backoff sleep calls
        mock_sleep.assert_any_call(0.1)
        mock_sleep.assert_any_call(0.2)
        self.assertEqual(mock_sleep.call_count, 2)

if __name__ == '__main__':
    unittest.main()
