import unittest
import sys
import os
import datetime
from unittest.mock import MagicMock, patch

# Setup paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
OPENALGO_ROOT = os.path.join(PROJECT_ROOT, 'openalgo')
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, OPENALGO_ROOT)

# Set dummy env vars
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from openalgo.utils.symbol_resolver import SymbolResolver
from openalgo.database.symbol import SymToken

class TestSymbolResolver(unittest.TestCase):

    def setUp(self):
        # Mock DB session
        self.patcher = patch('openalgo.utils.symbol_resolver.db_session')
        self.mock_session = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_parse_expiry(self):
        self.assertEqual(SymbolResolver.parse_expiry("26-DEC-24"), datetime.date(2024, 12, 26))
        self.assertEqual(SymbolResolver.parse_expiry("26-Dec-2024"), datetime.date(2024, 12, 26))
        self.assertIsNone(SymbolResolver.parse_expiry("INVALID"))

    def test_resolve_mcx_mini(self):
        # Mock Query
        mock_query = self.mock_session.query.return_value
        mock_filter = mock_query.filter.return_value

        # Setup Mock Results
        future_date = datetime.date.today() + datetime.timedelta(days=10)
        expiry_str = future_date.strftime("%d-%b-%y").upper()

        token1 = MagicMock(symbol="CRUDEOIL24DECFUT", expiry=expiry_str, lotsize=100, exchange="MCX", token="123")
        token2 = MagicMock(symbol="CRUDEOILM24DECFUT", expiry=expiry_str, lotsize=10, exchange="MCX", token="124")

        # Return both for the query
        mock_filter.all.return_value = [token1, token2]

        # Test Prefer Mini
        result = SymbolResolver.resolve_mcx_symbol("CRUDEOIL", prefer_mini=True)
        self.assertIsNotNone(result)
        self.assertEqual(result['symbol'], "CRUDEOILM24DECFUT")
        self.assertEqual(result['lotsize'], 10)

        # Test Standard
        result = SymbolResolver.resolve_mcx_symbol("CRUDEOIL", prefer_mini=False)
        self.assertIsNotNone(result)
        self.assertEqual(result['symbol'], "CRUDEOIL24DECFUT")

if __name__ == '__main__':
    unittest.main()
