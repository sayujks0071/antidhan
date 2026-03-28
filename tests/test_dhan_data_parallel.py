import time
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import pandas as pd
import sys
import os
import shutil

# Ensure openalgo root is in path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, repo_root)
sys.path.insert(0, os.path.join(repo_root, 'openalgo'))

from openalgo.broker.dhan_sandbox.api.data import BrokerData

class TestDhanDataParallel(unittest.TestCase):
    def setUp(self):
        # Clean up cache
        if os.path.exists(".cache/history"):
            shutil.rmtree(".cache/history")

        self.broker = BrokerData("dummy_token")

    def tearDown(self):
        # Clean up cache
        if os.path.exists(".cache/history"):
            shutil.rmtree(".cache/history")

    @patch('openalgo.broker.dhan_sandbox.api.data.get_token')
    @patch('openalgo.broker.dhan_sandbox.api.data.get_api_response')
    def test_get_history_parallel(self, mock_get_api_response, mock_get_token):
        # Mock token retrieval
        mock_get_token.return_value = "12345"

        # Mock API response for 5-day chunks
        # Each call returns 5 days of data
        def side_effect(*args, **kwargs):
            time.sleep(0.1)  # Simulate 100ms latency per request
            # Return dummy candle data
            return {
                "timestamp": [1672531200], # Some timestamp
                "open": [100],
                "high": [105],
                "low": [95],
                "close": [102],
                "volume": [1000],
                "open_interest": [500]
            }

        mock_get_api_response.side_effect = side_effect

        start_time = time.time()

        # Request 30 days of data (should result in ~6 chunks of 5 days)
        # Sequential: 6 * 0.1s = 0.6s
        # Parallel (max_workers=5): 2 rounds (5 + 1) -> ~0.2s

        start_date = "2026-01-01"
        end_date = "2026-01-30"

        try:
            df = self.broker.get_history(
                symbol="NIFTY",
                exchange="NSE",
                interval="5m", # Intraday triggers chunk logic
                start_date=start_date,
                end_date=end_date
            )

            end_time = time.time()
            duration = end_time - start_time

            print(f"Fetch Duration: {duration:.4f}s")

            # Check if dataframe is populated
            self.assertFalse(df.empty, "DataFrame should not be empty")

            # Verify mock was called 6 times
            self.assertEqual(mock_get_api_response.call_count, 6)

            # Verify speedup (should be significantly faster than 0.6s)
            self.assertLess(duration, 0.45, f"Fetch took too long: {duration:.4f}s")

        except Exception as e:
            self.fail(f"get_history failed: {e}")

if __name__ == '__main__':
    unittest.main()
