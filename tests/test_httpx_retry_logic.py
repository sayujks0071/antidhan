import sys
import os
import time
import unittest
from unittest.mock import MagicMock, patch
import httpx

# Add openalgo to path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

# Set APP_MODE to standalone to avoid http2 requirement
os.environ["APP_MODE"] = "standalone"

from utils.httpx_client import request, get_httpx_client

class TestHttpxRetry(unittest.TestCase):
    def setUp(self):
        # Reset the global client
        from utils import httpx_client
        if httpx_client._httpx_client:
            httpx_client._httpx_client.close()
            httpx_client._httpx_client = None

    @patch('httpx.Client.request')
    def test_retry_on_500(self, mock_request):
        """Test that request retries on 500 error"""
        # Configure mock to return 500
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.headers = {}
        mock_response.http_version = "HTTP/1.1"
        mock_request.return_value = mock_response

        # Call request
        url = "http://test.com/api"
        response = request("GET", url, max_retries=2, backoff_factor=0.1)

        # Verify it was called 3 times (1 initial + 2 retries)
        self.assertEqual(mock_request.call_count, 3)
        self.assertEqual(response.status_code, 500)

    @patch('httpx.Client.request')
    def test_retry_on_connection_error(self, mock_request):
        """Test that request retries on connection error"""
        # Configure mock to raise RequestError
        mock_request.side_effect = httpx.RequestError("Connection failed")

        # Call request and expect exception
        with self.assertRaises(httpx.RequestError):
            request("GET", "http://test.com/api", max_retries=2, backoff_factor=0.1)

        # Verify it was called 3 times (1 initial + 2 retries)
        self.assertEqual(mock_request.call_count, 3)

    @patch('httpx.Client.request')
    def test_success_after_retry(self, mock_request):
        """Test that request succeeds after retry"""
        # Configure mock to fail once then succeed
        fail_response = MagicMock(spec=httpx.Response)
        fail_response.status_code = 500
        fail_response.headers = {}

        success_response = MagicMock(spec=httpx.Response)
        success_response.status_code = 200
        success_response.headers = {}
        success_response.http_version = "HTTP/1.1"

        mock_request.side_effect = [fail_response, success_response]

        # Call request
        response = request("GET", "http://test.com/api", max_retries=2, backoff_factor=0.1)

        # Verify it was called 2 times
        self.assertEqual(mock_request.call_count, 2)
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
