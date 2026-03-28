import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
import pandas as pd
import sys
import os

# Ensure openalgo root is in path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, repo_root)
sys.path.insert(0, os.path.join(repo_root, 'openalgo'))

from openalgo.strategies.utils.trading_utils import PositionManager

class TestPositionManagerCaching(unittest.TestCase):
    def setUp(self):
        # PositionManager saves state to file, so we should clean it up or mock it
        # But for this test, we are testing in-memory caching of ATR
        self.symbol = "TEST_SYMBOL"

        # Patch load_state to avoid file IO errors or side effects
        with patch.object(PositionManager, 'load_state'):
            self.pm = PositionManager(self.symbol)

        self.client = MagicMock()

        # Mock history response
        dates = pd.date_range(end=datetime.now(), periods=20)
        self.mock_df = pd.DataFrame({
            'high': [105] * 20,
            'low': [95] * 20,
            'close': [100] * 20
        }, index=dates)
        self.client.history.return_value = self.mock_df

    def test_get_monthly_atr_caching(self):
        # First call
        atr1 = self.pm.get_monthly_atr(self.client)

        # Verify client.history was called
        self.client.history.assert_called_once()
        self.assertIsNotNone(atr1)

        # Reset mock to verify second call doesn't trigger history fetch
        self.client.history.reset_mock()

        # Second call
        atr2 = self.pm.get_monthly_atr(self.client)

        # Verify client.history was NOT called
        self.client.history.assert_not_called()
        self.assertEqual(atr1, atr2)

    def test_get_monthly_atr_cache_expiry(self):
        # Manually set cache to an old date
        old_date = (datetime.now().date() - pd.Timedelta(days=1))
        self.pm.cached_monthly_atr = 10.0
        self.pm.last_atr_update = old_date

        # Call get_monthly_atr
        atr = self.pm.get_monthly_atr(self.client)

        # Verify client.history WAS called because cache expired
        self.client.history.assert_called_once()

        # Verify cache was updated
        self.assertEqual(self.pm.last_atr_update, datetime.now().date())

if __name__ == '__main__':
    unittest.main()
