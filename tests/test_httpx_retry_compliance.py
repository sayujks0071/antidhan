import unittest
from unittest.mock import MagicMock, patch
import httpx
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
import sys
import os

# Ensure openalgo is in path
sys.path.append(os.getcwd())
try:
    from openalgo.utils.httpx_client import request, get_httpx_client
except ImportError:
    sys.path.append(os.path.join(os.getcwd(), 'openalgo'))
    from openalgo.utils.httpx_client import request, get_httpx_client

class TestHttpxRetryCompliance(unittest.TestCase):

    def setUp(self):
        # Reset the global client before each test
        from openalgo.utils import httpx_client
        httpx_client._httpx_client = None

    @patch('openalgo.utils.httpx_client.get_httpx_client')
    @patch('time.sleep')
    def test_retry_on_500_error(self, mock_sleep, mock_get_client):
        """Verify that the client retries on 500 status code."""
        # Create a mock client
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock responses: 500, 500, 200 (Success)
        response_500 = httpx.Response(500)
        response_200 = httpx.Response(200, json={"status": "success"})
        mock_client.request.side_effect = [response_500, response_500, response_200]

        # Call request
        response = request("GET", "http://test.com/api", max_retries=3)

        # Assertions
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_client.request.call_count, 3) # Initial + 2 retries
        self.assertEqual(mock_sleep.call_count, 2) # Sleep called twice

    @patch('openalgo.utils.httpx_client.get_httpx_client')
    @patch('time.sleep')
    def test_retry_on_429_error_with_retry_after(self, mock_sleep, mock_get_client):
        """Verify that the client respects Retry-After header on 429."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock responses: 429 (Retry-After: 2), 200
        response_429 = httpx.Response(429, headers={"Retry-After": "2"})
        response_200 = httpx.Response(200)
        mock_client.request.side_effect = [response_429, response_200]

        # Call request
        request("GET", "http://test.com/api", max_retries=3)

        # Assertions
        # Check if sleep was called with max(backoff, retry_after)
        # First backoff is 0.5, retry_after is 2. So sleep(2.0)
        mock_sleep.assert_called_with(2.0)

    @patch('openalgo.utils.httpx_client.get_httpx_client')
    @patch('time.sleep')
    def test_retry_on_request_exception(self, mock_sleep, mock_get_client):
        """Verify that the client retries on httpx.RequestError (e.g. connection timeout)."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock side effect: Raise RequestError, then succeed
        mock_client.request.side_effect = [
            httpx.RequestError("Connection timeout"),
            httpx.Response(200)
        ]

        # Call request
        response = request("GET", "http://test.com/api", max_retries=3)

        # Assertions
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_client.request.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)

if __name__ == '__main__':
    unittest.main()
