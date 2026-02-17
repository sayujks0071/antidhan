import unittest
from unittest.mock import MagicMock, patch
import httpx
import time
import sys
import os

# Ensure openalgo is in path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

from openalgo.utils.httpx_client import retry_with_backoff

class TestHttpxRetry(unittest.TestCase):
    def test_retry_on_status_code(self):
        # Mock a function that returns a 500 response twice, then a 200 response
        mock_func = MagicMock()
        response_500 = httpx.Response(500)
        response_200 = httpx.Response(200)
        mock_func.side_effect = [response_500, response_500, response_200]

        @retry_with_backoff(max_retries=3, backoff_factor=0.01)
        def decorated_func():
            return mock_func()

        result = decorated_func()

        self.assertEqual(result.status_code, 200)
        self.assertEqual(mock_func.call_count, 3)

    def test_retry_exhausted(self):
        # Mock a function that always returns 500
        mock_func = MagicMock()
        response_500 = httpx.Response(500)
        mock_func.return_value = response_500

        @retry_with_backoff(max_retries=2, backoff_factor=0.01)
        def decorated_func():
            return mock_func()

        result = decorated_func()

        self.assertEqual(result.status_code, 500)
        self.assertEqual(mock_func.call_count, 3) # Initial + 2 retries

    def test_retry_on_exception(self):
        # Mock a function that raises an exception twice, then returns success
        mock_func = MagicMock()
        mock_func.side_effect = [httpx.RequestError("Error"), httpx.RequestError("Error"), "Success"]

        @retry_with_backoff(max_retries=3, backoff_factor=0.01)
        def decorated_func():
            return mock_func()

        result = decorated_func()

        self.assertEqual(result, "Success")
        self.assertEqual(mock_func.call_count, 3)

    @patch('openalgo.utils.httpx_client.time.sleep')
    def test_retry_after_header(self, mock_sleep):
        # Mock a function that returns 429 with Retry-After header
        mock_func = MagicMock()
        response_429 = httpx.Response(429, headers={'Retry-After': '2'})
        response_200 = httpx.Response(200)
        mock_func.side_effect = [response_429, response_200]

        @retry_with_backoff(max_retries=3, backoff_factor=0.01)
        def decorated_func():
            return mock_func()

        result = decorated_func()

        self.assertEqual(result.status_code, 200)
        self.assertEqual(mock_func.call_count, 2)

        # Verify sleep was called with at least 2 seconds (Retry-After)
        # Note: The code logic does max(backoff, retry_after)
        # 1st retry: backoff = 0.01 * 2^0 = 0.01. Retry-After = 2. Sleep = 2.
        args, _ = mock_sleep.call_args
        self.assertGreaterEqual(args[0], 2.0)

if __name__ == '__main__':
    unittest.main()
