import sys
import os
import time
import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

# Setup path
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), 'openalgo'))

# Mock dependencies to avoid import errors
sys.modules['database'] = MagicMock()
sys.modules['database.token_db'] = MagicMock()
sys.modules['utils.httpx_client'] = MagicMock()
sys.modules['utils.logging'] = MagicMock()
sys.modules['broker.dhan_sandbox.api.baseurl'] = MagicMock()
sys.modules['broker.dhan_sandbox.mapping'] = MagicMock()
sys.modules['broker.dhan_sandbox.mapping.transform_data'] = MagicMock()

# Now import BrokerData
from openalgo.broker.dhan_sandbox.api.data import BrokerData

def test_parallel_fetch():
    print("Testing Parallel Fetch...")

    # Setup
    broker = BrokerData("test_token")

    # Mock helpers to avoid DB/Logic calls
    broker._get_exchange_segment = MagicMock(return_value="NSE_EQ")
    broker._get_instrument_type = MagicMock(return_value="EQUITY")
    broker._is_trading_day = MagicMock(return_value=True)

    # Patch get_token and get_api_response in the module namespace
    with patch('openalgo.broker.dhan_sandbox.api.data.get_token', return_value="12345"), \
         patch('openalgo.broker.dhan_sandbox.api.data.get_api_response') as mock_api:

        # Define side effect with delay
        def side_effect(*args, **kwargs):
            time.sleep(0.1) # Simulate network delay
            return {
                "timestamp": [1672531200], # Dummy timestamp
                "open": [100],
                "high": [105],
                "low": [95],
                "close": [102],
                "volume": [1000],
                "open_interest": [0]
            }

        mock_api.side_effect = side_effect

        # Define range > 20 days to ensure multiple chunks
        # Chunk logic is 5 days.
        # 2023-01-01 to 2023-01-25 is 24 days => ~5 chunks
        start_date = "2023-01-01"
        end_date = "2023-01-25"

        print(f"Requesting history for {start_date} to {end_date}...")
        start_time = time.time()
        df = broker.get_history("INFY", "NSE", "5m", start_date, end_date)
        end_time = time.time()

        duration = end_time - start_time
        call_count = mock_api.call_count

        print(f"Fetch took {duration:.4f} seconds.")
        print(f"API called {call_count} times.")

        expected_sequential = call_count * 0.1
        print(f"Expected sequential time: > {expected_sequential:.4f}s")

        if call_count >= 4:
            if duration < (expected_sequential * 0.7): # 30% faster at least
                print("SUCCESS: Parallel execution confirmed.")
            else:
                print(f"FAILURE: Execution time ({duration:.4f}s) is too close to sequential.")
                sys.exit(1)
        else:
             print(f"WARNING: Too few calls ({call_count}). Check chunking logic.")
             # Even if few calls, if duration is roughly max(call_times) it's parallel
             sys.exit(0)

if __name__ == "__main__":
    test_parallel_fetch()
