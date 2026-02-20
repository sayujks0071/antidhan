import time
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import sys
import os
from pathlib import Path

# Add repo root and openalgo to path to emulate the environment
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "openalgo"))
sys.path.insert(0, str(repo_root / "openalgo" / "strategies" / "utils"))

# Now utils should be importable if it corresponds to openalgo/utils
# But trading_utils.py has 'from utils import httpx_client'
# If openalgo/ is in path, 'import utils' imports openalgo/utils.

# We need to mock httpx_client because we don't want real network calls
# And we want to control the 'post' method.

# We can patch 'utils.httpx_client' if it is imported.
# But first we need to make sure 'utils' can be imported.
try:
    import utils
    import utils.httpx_client
except ImportError:
    # If it fails, we mock it in sys.modules
    mock_utils = MagicMock()
    mock_httpx = MagicMock()
    mock_utils.httpx_client = mock_httpx
    sys.modules['utils'] = mock_utils
    sys.modules['utils.httpx_client'] = mock_httpx

# Now import APIClient
try:
    from trading_utils import APIClient
except ImportError:
    from openalgo.strategies.utils.trading_utils import APIClient

class TestDataFetchingOptimization(unittest.TestCase):
    def setUp(self):
        self.client = APIClient(api_key="test_key")
        self.symbols = [f"SYM{i}" for i in range(10)]

    def test_batch_vs_serial_fetching(self):
        # We need to patch the httpx_client that APIClient uses.
        # It is imported in trading_utils as 'httpx_client'

        # We need to find where APIClient is defined to patch its global 'httpx_client'
        # Or patch 'utils.httpx_client' if that's what it uses.

        # APIClient uses 'httpx_client.post'

        with patch('utils.httpx_client.post') as mock_post:
             # Setup mock response
            def side_effect(*args, **kwargs):
                time.sleep(0.01) # Simulate network latency
                # Check if batch or single
                payload = kwargs.get('json', {})
                symbol = payload.get('symbol')

                mock_resp = MagicMock()
                mock_resp.status_code = 200

                if isinstance(symbol, list):
                    # Batch response
                    data = {s: {'ltp': 100} for s in symbol}
                    mock_resp.json.return_value = {"status": "success", "data": data}
                else:
                    # Single response
                    mock_resp.json.return_value = {"status": "success", "data": {'ltp': 100}}

                return mock_resp

            mock_post.side_effect = side_effect

            # 1. Serial Fetching
            start_time = time.time()
            for sym in self.symbols:
                self.client.get_quote(sym)
            serial_duration = time.time() - start_time
            print(f"Serial Duration (10 symbols): {serial_duration:.4f}s")

            # 2. Batch Fetching
            start_time = time.time()
            self.client.get_quote(self.symbols)
            batch_duration = time.time() - start_time
            print(f"Batch Duration (10 symbols): {batch_duration:.4f}s")

            # Verification
            self.assertLess(batch_duration, serial_duration)
            self.assertLess(batch_duration, 0.25) # Allow some buffer
            self.assertGreater(serial_duration, 0.1)

if __name__ == '__main__':
    unittest.main()
