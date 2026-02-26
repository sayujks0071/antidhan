
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime, timedelta

# Add path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

from openalgo.broker.dhan_sandbox.api.data import BrokerData

class TestParallelFetch(unittest.TestCase):
    def test_parallel_fetching(self):
        # Mock auth token
        broker = BrokerData("mock_token")

        # Mock internal methods
        broker._is_trading_day = MagicMock(return_value=True)
        broker._get_intraday_chunks = MagicMock(return_value=[
            ("2024-01-01", "2024-01-05"),
            ("2024-01-06", "2024-01-10"),
            ("2024-01-11", "2024-01-15")
        ])

        # Mock _fetch_intraday_chunk to return dummy data
        def mock_fetch(start, end, *args):
            return [{"timestamp": 123, "close": 100}]

        broker._fetch_intraday_chunk = MagicMock(side_effect=mock_fetch)

        # Mock get_token and exchange/instrument resolution
        with patch('openalgo.broker.dhan_sandbox.api.data.get_token', return_value="123"), \
             patch('openalgo.broker.dhan_sandbox.api.data.get_api_response'):

            df = broker.get_history(
                symbol="TEST",
                exchange="NSE",
                interval="5m",
                start_date="2024-01-01",
                end_date="2024-01-15"
            )

            # Assert that fetch was called multiple times (parallel or not, logic flow must be hit)
            self.assertTrue(broker._fetch_intraday_chunk.call_count >= 3)
            self.assertFalse(df.empty)
            print("Parallel fetch test passed!")

if __name__ == '__main__':
    unittest.main()
