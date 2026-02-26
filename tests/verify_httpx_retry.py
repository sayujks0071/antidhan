import unittest
import sys
import os
from unittest.mock import MagicMock, patch
import httpx

# Add repo root to path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Mock utils module BEFORE import
sys.modules['utils'] = MagicMock()
sys.modules['utils.logging'] = MagicMock()

# Import the module to test
from openalgo.utils.httpx_client import request, get_httpx_client

class TestHttpxRetry(unittest.TestCase):
    def setUp(self):
        # Reset the global client
        import openalgo.utils.httpx_client
        openalgo.utils.httpx_client._httpx_client = None

    @patch('openalgo.utils.httpx_client.get_httpx_client')
    def test_retry_on_500_error(self, mock_get_client):
        """Test that request retries on 500 server error"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Configure mock to return 500 error 3 times, then 200 OK
        # We need to mock request method of the client instance
        error_response = httpx.Response(500, request=httpx.Request("GET", "http://test.com"))
        success_response = httpx.Response(200, json={"status": "success"}, request=httpx.Request("GET", "http://test.com"))

        mock_client.request.side_effect = [error_response, error_response, error_response, success_response]

        # Call request function
        response = request("GET", "http://test.com", max_retries=3, backoff_factor=0.01)

        # Verify it was called 4 times (1 initial + 3 retries)
        self.assertEqual(mock_client.request.call_count, 4)
        self.assertEqual(response.status_code, 200)

    @patch('openalgo.utils.httpx_client.get_httpx_client')
    def test_retry_on_429_error(self, mock_get_client):
        """Test that request retries on 429 rate limit error"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Configure mock to return 429 error 2 times, then 200 OK
        error_response = httpx.Response(429, request=httpx.Request("GET", "http://test.com"))
        success_response = httpx.Response(200, json={"status": "success"}, request=httpx.Request("GET", "http://test.com"))

        mock_client.request.side_effect = [error_response, error_response, success_response]

        # Call request function
        response = request("GET", "http://test.com", max_retries=3, backoff_factor=0.01)

        # Verify it was called 3 times (1 initial + 2 retries)
        self.assertEqual(mock_client.request.call_count, 3)
        self.assertEqual(response.status_code, 200)

    @patch('openalgo.utils.httpx_client.get_httpx_client')
    def test_failure_after_max_retries(self, mock_get_client):
        """Test that request fails after max retries"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Configure mock to always return 500 error
        error_response = httpx.Response(500, request=httpx.Request("GET", "http://test.com"))
        mock_client.request.return_value = error_response

        # Call request function
        response = request("GET", "http://test.com", max_retries=3, backoff_factor=0.01)

        # Verify it was called 4 times (1 initial + 3 retries)
        self.assertEqual(mock_client.request.call_count, 4)
        self.assertEqual(response.status_code, 500)

    @patch('openalgo.utils.httpx_client.get_httpx_client')
    def test_no_retry_on_400_error(self, mock_get_client):
        """Test that request does NOT retry on 400 client error"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Configure mock to return 400 error
        error_response = httpx.Response(400, request=httpx.Request("GET", "http://test.com"))
        mock_client.request.return_value = error_response

        # Call request function
        response = request("GET", "http://test.com", max_retries=3, backoff_factor=0.01)

        # Verify it was called only once
        self.assertEqual(mock_client.request.call_count, 1)
        self.assertEqual(response.status_code, 400)

    @patch('openalgo.utils.httpx_client.get_httpx_client')
    def test_retry_connection_error(self, mock_get_client):
        """Test that request retries on connection error"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Configure mock to raise RequestError 2 times, then return success
        success_response = httpx.Response(200, json={"status": "success"}, request=httpx.Request("GET", "http://test.com"))

        mock_client.request.side_effect = [
            httpx.RequestError("Connection failed"),
            httpx.RequestError("Connection failed"),
            success_response
        ]

        # Call request function
        response = request("GET", "http://test.com", max_retries=3, backoff_factor=0.01)

        # Verify it was called 3 times
        self.assertEqual(mock_client.request.call_count, 3)
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
