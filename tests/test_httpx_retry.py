import unittest
from unittest.mock import patch
import httpx
import sys
# Test suite for httpx retry logic
import os

# Add openalgo to sys.path so 'utils' can be imported as expected by the module
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

from utils.httpx_client import request, cleanup_httpx_client

class TestHttpxRetry(unittest.TestCase):
    def setUp(self):
        cleanup_httpx_client()

    def tearDown(self):
        cleanup_httpx_client()

    @patch('utils.httpx_client.time.sleep')
    @patch('httpx.Client.request')
    def test_retry_on_500_error(self, mock_request, mock_sleep):
        # Setup mock to fail twice with 500, then succeed
        response_fail = httpx.Response(500, request=httpx.Request("GET", "http://test.com"))
        response_success = httpx.Response(200, request=httpx.Request("GET", "http://test.com"))

        mock_request.side_effect = [response_fail, response_fail, response_success]

        # Call request with retries
        response = request("GET", "http://test.com", max_retries=3, backoff_factor=0.1)

        # Verify result
        self.assertEqual(response.status_code, 200)

        # Verify retries
        self.assertEqual(mock_request.call_count, 3)

        # Verify backoff sleep calls
        # 1st retry: sleep(0.1 * 2^0) = 0.1
        # 2nd retry: sleep(0.1 * 2^1) = 0.2
        mock_sleep.assert_any_call(0.1)
        mock_sleep.assert_any_call(0.2)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch('utils.httpx_client.time.sleep')
    @patch('httpx.Client.request')
    def test_retry_on_429_error(self, mock_request, mock_sleep):
        # Setup mock to fail once with 429, then succeed
        response_fail = httpx.Response(429, request=httpx.Request("GET", "http://test.com"))
        response_success = httpx.Response(200, request=httpx.Request("GET", "http://test.com"))

        mock_request.side_effect = [response_fail, response_success]

        response = request("GET", "http://test.com", max_retries=3, backoff_factor=0.1)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_request.call_count, 2)
        mock_sleep.assert_called_with(0.1)

    @patch('utils.httpx_client.time.sleep')
    @patch('httpx.Client.request')
    def test_max_retries_exceeded(self, mock_request, mock_sleep):
        # Setup mock to fail always
        response_fail = httpx.Response(500, request=httpx.Request("GET", "http://test.com"))
        mock_request.return_value = response_fail

        response = request("GET", "http://test.com", max_retries=2, backoff_factor=0.1)

        self.assertEqual(response.status_code, 500)
        # Initial + 2 retries = 3 calls
        self.assertEqual(mock_request.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch('utils.httpx_client.time.sleep')
    @patch('httpx.Client.request')
    def test_network_error_retry(self, mock_request, mock_sleep):
        # Setup mock to raise RequestError twice, then succeed
        mock_request.side_effect = [
            httpx.RequestError("Connection failed"),
            httpx.RequestError("Timeout"),
            httpx.Response(200, request=httpx.Request("GET", "http://test.com"))
        ]

        response = request("GET", "http://test.com", max_retries=3, backoff_factor=0.1)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_request.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

if __name__ == '__main__':
    unittest.main()
