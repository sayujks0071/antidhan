import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime
import sys
import os

# Add openalgo root to path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))
sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'utils'))

from trading_utils import APIClient

class TestAPIClientHistory(unittest.TestCase):
    def setUp(self):
        self.client = APIClient(api_key="TEST")
        # Mock the cache to avoid filesystem I/O
        self.client.cache = MagicMock()
        self.client.cache.get.return_value = None

    @patch('trading_utils.httpx_client.post')
    def test_history_smart_caching(self, mock_post):
        # Mock API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": [
                {"timestamp": 1704067200, "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000}, # 2024-01-01
            ]
        }
        mock_post.return_value = mock_response

        # Call history
        df = self.client.history("TEST", start_date="2024-01-01", end_date="2024-01-02")

        # Verify result
        self.assertFalse(df.empty)
        self.assertEqual(len(df), 1)

        # Verify API called
        self.assertTrue(mock_post.called)

        # Verify cache set
        self.client.cache.set.assert_called()

if __name__ == '__main__':
    unittest.main()
