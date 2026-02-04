import unittest
from unittest.mock import MagicMock, patch
import httpx
import sys
import os

# Add openalgo to path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

from strategies.utils.trading_utils import APIClient

class TestRetryLogic(unittest.TestCase):
    def setUp(self):
        self.api_client = APIClient(api_key="test_key")

    @patch('utils.httpx_client.get_httpx_client')
    def test_placesmartorder_retry_success(self, mock_get_client):
        # Mock the client and its request method
        mock_client_instance = MagicMock()
        mock_get_client.return_value = mock_client_instance

        # Setup request side effects: 2 failures, then success
        # Failures raise RequestError
        error = httpx.RequestError("Connection failed", request=MagicMock())
        success_response = MagicMock(spec=httpx.Response)
        success_response.status_code = 200
        success_response.json.return_value = {"status": "success", "orderid": "123"}
        success_response.http_version = "HTTP/1.1"
        success_response.request.extensions = {} # used by log_response hook

        mock_client_instance.request.side_effect = [error, error, success_response]

        # Call placesmartorder
        # Note: placesmartorder passes max_retries=3, backoff_factor=1.0
        # We want to verify it succeeds eventually
        result = self.api_client.placesmartorder(
            strategy="test_strat",
            symbol="TEST",
            action="BUY",
            exchange="NSE",
            price_type="MARKET",
            product="MIS",
            quantity=1,
            position_size=1
        )

        # Assertions
        self.assertEqual(result.get("status"), "success")
        self.assertEqual(result.get("orderid"), "123")
        # Should have called request 3 times
        self.assertEqual(mock_client_instance.request.call_count, 3)

    @patch('utils.httpx_client.get_httpx_client')
    def test_placesmartorder_retry_failure(self, mock_get_client):
        # Mock the client
        mock_client_instance = MagicMock()
        mock_get_client.return_value = mock_client_instance

        # Setup request side effects: all failures
        error = httpx.RequestError("Persistent failure", request=MagicMock())
        mock_client_instance.request.side_effect = error

        # Call placesmartorder
        result = self.api_client.placesmartorder(
            strategy="test_strat",
            symbol="TEST",
            action="BUY",
            exchange="NSE",
            price_type="MARKET",
            product="MIS",
            quantity=1,
            position_size=1
        )

        # Assertions
        # placesmartorder catches exceptions and returns error dict
        self.assertEqual(result.get("status"), "error")
        # APIClient.placesmartorder catches the exception.
        # httpx_client.request re-raises the exception after retries.
        # So placesmartorder catches it.
        self.assertIn("Persistent failure", result.get("message"))
        # Should have called request 4 times (initial + 3 retries)
        self.assertEqual(mock_client_instance.request.call_count, 4)

    @patch('utils.httpx_client.get_httpx_client')
    def test_placesmartorder_status_retry(self, mock_get_client):
        # Mock the client
        mock_client_instance = MagicMock()
        mock_get_client.return_value = mock_client_instance

        # Setup request side effects: 502 error then 200 OK
        error_response = MagicMock(spec=httpx.Response)
        error_response.status_code = 502
        error_response.http_version = "HTTP/1.1"
        error_response.request.extensions = {}

        success_response = MagicMock(spec=httpx.Response)
        success_response.status_code = 200
        success_response.json.return_value = {"status": "success"}
        success_response.http_version = "HTTP/1.1"
        success_response.request.extensions = {}

        mock_client_instance.request.side_effect = [error_response, success_response]

        # Call placesmartorder
        result = self.api_client.placesmartorder(
            strategy="test_strat",
            symbol="TEST",
            action="BUY",
            exchange="NSE",
            price_type="MARKET",
            product="MIS",
            quantity=1,
            position_size=1
        )

        # Assertions
        self.assertEqual(result.get("status"), "success")
        # Should have called request 2 times
        self.assertEqual(mock_client_instance.request.call_count, 2)

if __name__ == '__main__':
    unittest.main()
