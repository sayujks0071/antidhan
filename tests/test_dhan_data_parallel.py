import sys
import os
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import pandas as pd

# Add project root to path
sys.path.insert(0, os.path.abspath(os.getcwd()))

# Mock modules before importing BrokerData to avoid dependency issues
sys.modules['database.token_db'] = MagicMock()
sys.modules['utils.httpx_client'] = MagicMock()
sys.modules['utils.logging'] = MagicMock()
sys.modules['broker.dhan_sandbox.api.baseurl'] = MagicMock()
sys.modules['broker.dhan_sandbox.mapping.transform_data'] = MagicMock()

# Now import the target module
from openalgo.broker.dhan_sandbox.api.data import BrokerData

class TestDhanDataParallel(unittest.TestCase):
    def setUp(self):
        self.broker = BrokerData("dummy_token")
        self.broker._get_exchange_segment = MagicMock(return_value="NSE_EQ")
        self.broker._get_instrument_type = MagicMock(return_value="EQUITY")
        # Mock token_db functions that are imported directly in data.py
        patcher = patch('openalgo.broker.dhan_sandbox.api.data.get_token', return_value="12345")
        self.mock_get_token = patcher.start()
        self.addCleanup(patcher.stop)

    @patch('openalgo.broker.dhan_sandbox.api.data.get_api_response')
    def test_get_history_parallel(self, mock_get_api_response):
        # Setup mock response generator
        def side_effect(endpoint, auth, method, payload):
            # Parse payload to get dates
            import json
            data = json.loads(payload)
            from_date = data.get('fromDate') # YYYY-MM-DD

            # Generate dummy candles for this chunk
            timestamps = []
            opens = []
            closes = []

            # Create 1 candle
            dt = datetime.strptime(from_date, "%Y-%m-%d")
            ts = dt.timestamp()
            timestamps.append(ts)
            opens.append(100.0)
            closes.append(101.0)

            return {
                "status": "success",
                "timestamp": timestamps,
                "open": opens,
                "high": opens,
                "low": opens,
                "close": closes,
                "volume": [100],
                "open_interest": [0]
            }

        mock_get_api_response.side_effect = side_effect

        # Call get_history for a 20 day range (should trigger multiple chunks)
        start_date = "2023-01-01"
        end_date = "2023-01-20"

        # Ensure dates are treated as trading days (mock _is_trading_day)
        self.broker._is_trading_day = MagicMock(return_value=True)
        self.broker._get_intraday_time_range = MagicMock(side_effect=lambda d: (d, d))
        self.broker._convert_timestamp_to_ist = MagicMock(side_effect=lambda ts, is_daily=False: int(ts))

        df = self.broker.get_history("RELIANCE", "NSE", "5m", start_date, end_date)

        # Verify results
        print(f"\nFetched {len(df)} rows.")
        self.assertTrue(len(df) > 0)

        # Verify multiple calls were made (20 days / 5 days chunk ~ 4 chunks)
        call_count = mock_get_api_response.call_count
        print(f"API Call Count: {call_count}")
        self.assertTrue(call_count >= 3, f"Expected at least 3 API calls, got {call_count}")

        # Verify sorting
        self.assertTrue(df['timestamp'].is_monotonic_increasing)

if __name__ == '__main__':
    unittest.main()
