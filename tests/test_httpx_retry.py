import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import httpx
import time

# Add path
current_dir = os.getcwd()
sys.path.insert(0, os.path.join(current_dir, "openalgo"))

from utils.httpx_client import request, cleanup_httpx_client

class TestHttpxRetry(unittest.TestCase):
    def setUp(self):
        cleanup_httpx_client()

    @patch('httpx.Client.request')
    def test_retry_on_500(self, mock_request):
        print("Testing retry on 500...")
        # Fail twice with 500, succeed on 3rd
        response_500 = httpx.Response(500, request=httpx.Request("GET", "http://test.com"))
        response_200 = httpx.Response(200, request=httpx.Request("GET", "http://test.com"))

        mock_request.side_effect = [response_500, response_500, response_200]

        # Call request with fast backoff for test
        response = request("GET", "http://test.com", max_retries=3, backoff_factor=0.01)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_request.call_count, 3)
        print("✅ Retry on 500: Passed")

    @patch('httpx.Client.request')
    def test_retry_on_timeout(self, mock_request):
        print("Testing retry on Timeout...")
        # Fail twice with Timeout, succeed on 3rd
        # httpx.RequestError covers TimeoutException
        mock_request.side_effect = [
            httpx.ReadTimeout("Timeout", request=httpx.Request("GET", "http://test.com")),
            httpx.ReadTimeout("Timeout", request=httpx.Request("GET", "http://test.com")),
            httpx.Response(200, request=httpx.Request("GET", "http://test.com"))
        ]

        response = request("GET", "http://test.com", max_retries=3, backoff_factor=0.01)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_request.call_count, 3)
        print("✅ Retry on Timeout: Passed")

    @patch('httpx.Client.request')
    def test_failure_after_retries(self, mock_request):
        print("Testing failure after retries...")
        # Fail always
        response_500 = httpx.Response(500, request=httpx.Request("GET", "http://test.com"))
        mock_request.return_value = response_500

        response = request("GET", "http://test.com", max_retries=2, backoff_factor=0.01)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(mock_request.call_count, 3) # Initial + 2 retries
        print("✅ Failure after retries: Passed")

if __name__ == '__main__':
    unittest.main()
