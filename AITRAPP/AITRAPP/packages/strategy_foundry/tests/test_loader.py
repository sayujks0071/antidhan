import os
import unittest

import pandas as pd

from packages.strategy_foundry.data.loader import DataLoader


class TestLoader(unittest.TestCase):
    def test_cache_path(self):
        loader = DataLoader()
        path = loader._get_cache_path('TEST')
        self.assertTrue(path.endswith('TEST.csv'))

    def test_normalize(self):
        # Create a dummy csv
        loader = DataLoader()
        df = pd.DataFrame({'Date': ['2023-01-01'], 'Close': [100]})
        path = loader._get_cache_path('TEST_Dummy')
        df.to_csv(path, index=False)

        # Load
        loaded = loader.get_data('TEST_Dummy', force_download=False)
        self.assertIn('datetime', loaded.columns)
        self.assertIn('close', loaded.columns)

        # Cleanup
        if os.path.exists(path):
            os.remove(path)

if __name__ == '__main__':
    unittest.main()
