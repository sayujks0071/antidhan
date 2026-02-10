import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import httpx
import time
from datetime import datetime, timedelta, timezone

# Add path
current_dir = os.getcwd()
sys.path.insert(0, os.path.join(current_dir, "openalgo"))

from utils.httpx_client import request, cleanup_httpx_client

class TestHttpxRetryAfter(unittest.TestCase):
    def setUp(self):
        cleanup_httpx_client()

    @patch('httpx.Client.request')
    @patch('time.sleep')
    def test_retry_after_integer(self, mock_sleep, mock_request):
        print("Testing retry with Retry-After (seconds)...")
        # Fail with 429 and Retry-After: 5
        headers = httpx.Headers({"Retry-After": "5"})
        response_429 = httpx.Response(429, headers=headers, request=httpx.Request("GET", "http://test.com"))
        response_200 = httpx.Response(200, request=httpx.Request("GET", "http://test.com"))

        mock_request.side_effect = [response_429, response_200]

        # Call request
        response = request("GET", "http://test.com", max_retries=3)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_request.call_count, 2)

        # Verify sleep was called with approx 5 seconds
        mock_sleep.assert_called_with(5.0)
        print("✅ Retry with Retry-After (seconds): Passed")

    @patch('httpx.Client.request')
    @patch('time.sleep')
    def test_retry_after_date(self, mock_sleep, mock_request):
        print("Testing retry with Retry-After (date)...")

        # Calculate a future date (10 seconds from now)
        # Using simple format that email.utils can parse
        future_time = datetime.now(timezone.utc) + timedelta(seconds=10)
        http_date = future_time.strftime("%a, %d %b %Y %H:%M:%S GMT")

        headers = httpx.Headers({"Retry-After": http_date})
        response_429 = httpx.Response(429, headers=headers, request=httpx.Request("GET", "http://test.com"))
        response_200 = httpx.Response(200, request=httpx.Request("GET", "http://test.com"))

        mock_request.side_effect = [response_429, response_200]

        response = request("GET", "http://test.com", max_retries=3)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_request.call_count, 2)

        # Verify sleep was called
        args, _ = mock_sleep.call_args
        wait_time = args[0]
        # Should be around 10 seconds, allow margin for execution time
        self.assertTrue(8.0 <= wait_time <= 12.0, f"Wait time {wait_time} not close to 10s")
        print("✅ Retry with Retry-After (date): Passed")

if __name__ == '__main__':
    unittest.main()
