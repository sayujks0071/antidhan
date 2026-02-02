import unittest
from unittest.mock import MagicMock, patch
import httpx
import sys
import os
import pandas as pd
import json

# Add openalgo to path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

from strategies.utils.trading_utils import APIClient
from utils import httpx_client

class TestTradingUtilsRefactor(unittest.TestCase):
    def setUp(self):
        self.api_client = APIClient(api_key="test_key")

    @patch('utils.httpx_client.get_httpx_client')
    def test_history_retry(self, mock_get_client):
        mock_client_instance = MagicMock()
        mock_get_client.return_value = mock_client_instance

        # 1. Timeout, 2. Success
        error = httpx.TimeoutException("Timeout", request=MagicMock())
        success_response = MagicMock(spec=httpx.Response)
        success_response.status_code = 200
        success_response.json.return_value = {
            "status": "success",
            "data": [{"timestamp": 1600000000, "close": 100}]
        }
        success_response.http_version = "HTTP/1.1"
        success_response.request.extensions = {}

        mock_client_instance.request.side_effect = [error, success_response]

        df = self.api_client.history("TEST")

        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 1)
        # Should call request 2 times
        self.assertEqual(mock_client_instance.request.call_count, 2)

    @patch('utils.httpx_client.get_httpx_client')
    def test_get_quote_retry(self, mock_get_client):
        mock_client_instance = MagicMock()
        mock_get_client.return_value = mock_client_instance

        # 1. 500 Error, 2. Success
        error_response = MagicMock(spec=httpx.Response)
        error_response.status_code = 500
        error_response.http_version = "HTTP/1.1"
        error_response.request.extensions = {}

        success_response = MagicMock(spec=httpx.Response)
        success_response.status_code = 200
        success_response.json.return_value = {
            "status": "success",
            "data": {"ltp": 100.5}
        }
        success_response.http_version = "HTTP/1.1"
        success_response.request.extensions = {}
        success_response.text = json.dumps(success_response.json.return_value)

        mock_client_instance.request.side_effect = [error_response, success_response]

        quote = self.api_client.get_quote("TEST")

        self.assertEqual(quote['ltp'], 100.5)
        self.assertEqual(mock_client_instance.request.call_count, 2)

    @patch('utils.httpx_client.get_httpx_client')
    def test_get_instruments_retry(self, mock_get_client):
        mock_client_instance = MagicMock()
        mock_get_client.return_value = mock_client_instance

        # 1. Connection Error, 2. Success
        error = httpx.RequestError("Conn Error", request=MagicMock())
        success_response = MagicMock(spec=httpx.Response)
        success_response.status_code = 200
        success_response.text = "symbol,name\nTEST,Test Instrument"
        success_response.http_version = "HTTP/1.1"
        success_response.request.extensions = {}

        mock_client_instance.request.side_effect = [error, success_response]

        df = self.api_client.get_instruments()

        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 1)
        self.assertEqual(mock_client_instance.request.call_count, 2)

if __name__ == '__main__':
    unittest.main()
