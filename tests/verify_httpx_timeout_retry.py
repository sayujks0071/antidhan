import unittest
from unittest.mock import MagicMock, patch
import httpx
import time

# We need to import the module to test
# Since we can't easily import from utils without path setup:
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../openalgo')))

from utils.httpx_client import request, get_httpx_client, cleanup_httpx_client

class TestHttpxTimeoutRetry(unittest.TestCase):
    def setUp(self):
        # Clean up any existing client
        cleanup_httpx_client()

    def tearDown(self):
        cleanup_httpx_client()

    @patch('utils.httpx_client._create_http_client')
    @patch('time.sleep')
    def test_retry_on_timeout(self, mock_sleep, mock_create_client):
        # Create a mock client
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        # Setup the mock client to raise TimeoutException twice, then succeed
        # httpx.TimeoutException is a subclass of httpx.RequestError
        timeout_exc = httpx.TimeoutException("Connection timed out")

        # Mock Response for success
        success_response = MagicMock(spec=httpx.Response)
        success_response.status_code = 200
        success_response.http_version = "HTTP/1.1"
        success_response.request = MagicMock()
        success_response.request.extensions = {}

        # side_effect: raise, raise, return
        mock_client.request.side_effect = [timeout_exc, timeout_exc, success_response]

        # Call request
        response = request("GET", "http://test.com", max_retries=3, backoff_factor=0.1)

        # Assertions
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_client.request.call_count, 3) # Initial + 2 retries
        self.assertEqual(mock_sleep.call_count, 2) # Sleep after each failure

    @patch('utils.httpx_client._create_http_client')
    @patch('time.sleep')
    def test_max_retries_exceeded(self, mock_sleep, mock_create_client):
        # Create a mock client
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        timeout_exc = httpx.TimeoutException("Connection timed out")

        # side_effect: always raise
        mock_client.request.side_effect = timeout_exc

        # Call request and expect exception
        with self.assertRaises(httpx.RequestError):
            request("GET", "http://test.com", max_retries=2, backoff_factor=0.1)

        self.assertEqual(mock_client.request.call_count, 3) # Initial + 2 retries
        self.assertEqual(mock_sleep.call_count, 2)

if __name__ == '__main__':
    unittest.main()
