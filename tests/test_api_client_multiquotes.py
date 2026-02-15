import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import json

# Add openalgo directory to path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

from strategies.utils.trading_utils import APIClient

class TestAPIClientMultiQuotes(unittest.TestCase):
    @patch('strategies.utils.trading_utils.httpx_client')
    def test_get_quote_list(self, mock_httpx):
        client = APIClient(api_key="TEST_KEY", host="http://test")

        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        data = {
            "status": "success",
            "data": {
                "INFY": {"ltp": 1500},
                "TCS": {"ltp": 3500}
            }
        }
        mock_response.json.return_value = data
        mock_response.text = json.dumps(data) # IMPORTANT: trading_utils checks .text

        mock_httpx.post.return_value = mock_response

        symbols = ["INFY", "TCS"]
        exchange = "NSE"

        result = client.get_quote(symbols, exchange)

        # Verify result
        self.assertEqual(result, {"INFY": {"ltp": 1500}, "TCS": {"ltp": 3500}})

        # Verify call arguments
        mock_httpx.post.assert_called_once()
        args, kwargs = mock_httpx.post.call_args

        url = args[0]
        json_payload = kwargs['json']

        self.assertEqual(url, "http://test/api/v1/multiquotes")
        self.assertEqual(json_payload['apikey'], "TEST_KEY")
        self.assertEqual(len(json_payload['symbols']), 2)
        self.assertEqual(json_payload['symbols'][0], {"symbol": "INFY", "exchange": "NSE"})
        self.assertEqual(json_payload['symbols'][1], {"symbol": "TCS", "exchange": "NSE"})

    @patch('strategies.utils.trading_utils.httpx_client')
    def test_get_quote_single(self, mock_httpx):
        client = APIClient(api_key="TEST_KEY", host="http://test")

        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        data = {
            "status": "success",
            "data": {"ltp": 1500}
        }
        mock_response.json.return_value = data
        mock_response.text = json.dumps(data)

        mock_httpx.post.return_value = mock_response

        symbol = "INFY"
        exchange = "NSE"

        result = client.get_quote(symbol, exchange)

        # Verify result
        self.assertEqual(result, {"ltp": 1500})

        # Verify call arguments
        mock_httpx.post.assert_called_once()
        args, kwargs = mock_httpx.post.call_args

        url = args[0]
        json_payload = kwargs['json']

        self.assertEqual(url, "http://test/api/v1/quotes")
        self.assertEqual(json_payload['apikey'], "TEST_KEY")
        self.assertEqual(json_payload['symbol'], "INFY")
        self.assertEqual(json_payload['exchange'], "NSE")

if __name__ == '__main__':
    unittest.main()
