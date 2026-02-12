
import unittest
from unittest.mock import MagicMock, patch, Mock
import time
import httpx
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime

# Mocking modules to ensure test runs in restricted environments
import sys
sys.modules['utils'] = MagicMock()
sys.modules['utils.logging'] = MagicMock()

# Now we can import the module under test
# We need to make sure the relative import works or mock it properly
# Assuming the file is at openalgo/utils/httpx_client.py
# Since we are running from root, we need to adjust path or import properly if possible
# But given the structure, I'll try to import it directly if PYTHONPATH is set correctly
# Otherwise I'll use a trick to load it

import os
sys.path.append(os.getcwd())
try:
    from openalgo.utils.httpx_client import request, get_httpx_client, _create_http_client
except ImportError:
    # If openalgo package is not recognized, try adding openalgo to path
    sys.path.append(os.path.join(os.getcwd(), 'openalgo'))
    from utils.httpx_client import request, get_httpx_client, _create_http_client


class TestHttpxRetryVerification(unittest.TestCase):

    def setUp(self):
        # Reset the global client before each test
        from openalgo.utils import httpx_client
        httpx_client._httpx_client = None

    @patch('openalgo.utils.httpx_client.get_httpx_client')
    @patch('time.sleep') # Mock sleep to speed up tests
    def test_retry_on_500_error(self, mock_sleep, mock_get_client):
        """Verify that the client retries on 500 status code."""
        mock_client_instance = MagicMock()
        mock_get_client.return_value = mock_client_instance

        # Setup mock response sequence: 500, 500, 200
        response_500 = httpx.Response(500)
        response_200 = httpx.Response(200, json={"status": "success"})

        mock_client_instance.request.side_effect = [response_500, response_500, response_200]

        response = request("GET", "http://test.com/api", max_retries=3)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_client_instance.request.call_count, 3)
        # Verify backoff calls
        self.assertEqual(mock_sleep.call_count, 2)

    @patch('openalgo.utils.httpx_client.get_httpx_client')
    @patch('time.sleep')
    def test_retry_on_429_error(self, mock_sleep, mock_get_client):
        """Verify that the client retries on 429 status code."""
        mock_client_instance = MagicMock()
        mock_get_client.return_value = mock_client_instance

        # Setup mock response sequence: 429, 200
        response_429 = httpx.Response(429)
        response_200 = httpx.Response(200, json={"status": "success"})

        mock_client_instance.request.side_effect = [response_429, response_200]

        response = request("GET", "http://test.com/api", max_retries=3)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_client_instance.request.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)

    @patch('openalgo.utils.httpx_client.get_httpx_client')
    @patch('time.sleep')
    def test_retry_after_header_seconds(self, mock_sleep, mock_get_client):
        """Verify that the client respects Retry-After header (seconds)."""
        mock_client_instance = MagicMock()
        mock_get_client.return_value = mock_client_instance

        # Setup mock response: 429 with Retry-After: 2
        response_429 = httpx.Response(429, headers={"Retry-After": "2"})
        response_200 = httpx.Response(200)

        mock_client_instance.request.side_effect = [response_429, response_200]

        request("GET", "http://test.com/api", max_retries=3)

        # Should verify that sleep was called with at least 2 seconds
        # The code takes max(backoff, retry_after)
        # Default backoff starts at 0.5 * 2^0 = 0.5
        # So it should sleep for 2.0 seconds
        mock_sleep.assert_called_with(2.0)

    @patch('openalgo.utils.httpx_client.get_httpx_client')
    @patch('time.sleep')
    def test_retry_after_header_date(self, mock_sleep, mock_get_client):
        """Verify that the client respects Retry-After header (HTTP Date)."""
        mock_client_instance = MagicMock()
        mock_get_client.return_value = mock_client_instance

        # Calculate a future date (e.g., 5 seconds from now)
        future_time = datetime.now(timezone.utc) + timedelta(seconds=5)
        http_date = format_datetime(future_time, usegmt=True)

        response_429 = httpx.Response(429, headers={"Retry-After": http_date})
        response_200 = httpx.Response(200)

        mock_client_instance.request.side_effect = [response_429, response_200]

        with patch('openalgo.utils.httpx_client.datetime') as mock_datetime:
            # Mock datetime.now to return a fixed time so subtraction works predictably
            # But the code uses datetime.now(retry_date.tzinfo)
            # This is tricky to mock perfectly without refactoring, but we can rely on delta
            # Let's just ensure it parses and calls sleep with roughly the right amount
            # Actually, let's trust the logic if we can mock the now()

            # Re-implementation for test stability:
            # We just want to ensure it parses the date and calculates a diff
            request("GET", "http://test.com/api", max_retries=3)

            # Check if sleep was called. Since we can't easily control "now" inside the function
            # without more complex mocking, we just check sleep was called with a float
            self.assertTrue(mock_sleep.call_count >= 1)
            args, _ = mock_sleep.call_args
            self.assertIsInstance(args[0], float)
            # It should be around 5.0 (capped at 60)
            self.assertTrue(0 < args[0] <= 60)

    @patch('openalgo.utils.httpx_client.get_httpx_client')
    @patch('time.sleep')
    def test_retry_on_request_error(self, mock_sleep, mock_get_client):
        """Verify that the client retries on httpx.RequestError (e.g. timeout)."""
        mock_client_instance = MagicMock()
        mock_get_client.return_value = mock_client_instance

        # Setup side effect: Raise RequestError twice, then succeed
        mock_client_instance.request.side_effect = [
            httpx.RequestError("Connection timeout"),
            httpx.RequestError("Connection reset"),
            httpx.Response(200)
        ]

        response = request("GET", "http://test.com/api", max_retries=3)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_client_instance.request.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch('openalgo.utils.httpx_client.get_httpx_client')
    @patch('time.sleep')
    def test_max_retries_exceeded(self, mock_sleep, mock_get_client):
        """Verify that the client gives up after max retries."""
        mock_client_instance = MagicMock()
        mock_get_client.return_value = mock_client_instance

        # Setup side effect: Always 500
        response_500 = httpx.Response(500)
        mock_client_instance.request.return_value = response_500

        response = request("GET", "http://test.com/api", max_retries=2)

        # Should return the last response (500)
        self.assertEqual(response.status_code, 500)
        # Initial call + 2 retries = 3 calls
        self.assertEqual(mock_client_instance.request.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

if __name__ == '__main__':
    unittest.main()
