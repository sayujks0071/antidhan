import unittest
import os
import pandas as pd
from datetime import datetime, timedelta
from openalgo.strategies.utils.symbol_resolver import SymbolResolver

class TestSymbolResolver(unittest.TestCase):
    def setUp(self):
        # Create dummy instruments file
        self.csv_path = 'test_instruments.csv'
        now = datetime.now()

        # Ensure expiries are in same month for option test
        self.d1, self.d2 = 1, 5
        t1 = now + timedelta(days=self.d1)
        t2 = now + timedelta(days=self.d2)
        if t1.month != t2.month:
            self.d1 += 20
            self.d2 += 20

        data = [
            {'exchange': 'NSE', 'token': '1', 'symbol': 'RELIANCE', 'name': 'RELIANCE', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ'},
            {'exchange': 'NSE', 'token': '2', 'symbol': 'NIFTY', 'name': 'NIFTY', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ'},
            # Futures
            {'exchange': 'NSE', 'token': '3', 'symbol': 'NIFTY23OCTFUT', 'name': 'NIFTY', 'expiry': (now + timedelta(days=10)).strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'FUT'},
            {'exchange': 'MCX', 'token': '4', 'symbol': 'SILVERMIC23NOVFUT', 'name': 'SILVER', 'expiry': (now + timedelta(days=20)).strftime('%Y-%m-%d'), 'lot_size': 1, 'instrument_type': 'FUT'},
            {'exchange': 'MCX', 'token': '5', 'symbol': 'SILVER23NOVFUT', 'name': 'SILVER', 'expiry': (now + timedelta(days=20)).strftime('%Y-%m-%d'), 'lot_size': 30, 'instrument_type': 'FUT'},
            # Options
            {'exchange': 'NFO', 'token': '6', 'symbol': 'NIFTY23OCT19500CE', 'name': 'NIFTY', 'expiry': (now + timedelta(days=self.d1)).strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'OPT'},
            {'exchange': 'NFO', 'token': '7', 'symbol': 'NIFTY23OCT19500PE', 'name': 'NIFTY', 'expiry': (now + timedelta(days=self.d1)).strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'OPT'},
            {'exchange': 'NFO', 'token': '9', 'symbol': 'NIFTY23OCTMONTHLYCE', 'name': 'NIFTY', 'expiry': (now + timedelta(days=self.d2)).strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'OPT'},
            {'exchange': 'NFO', 'token': '8', 'symbol': 'NIFTY23NOV19500CE', 'name': 'NIFTY', 'expiry': (now + timedelta(days=60)).strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'OPT'},
        ]
        pd.DataFrame(data).to_csv(self.csv_path, index=False)
        self.resolver = SymbolResolver(self.csv_path)

    def tearDown(self):
        if os.path.exists(self.csv_path):
            os.remove(self.csv_path)

    def test_resolve_equity(self):
        res = self.resolver.resolve({'type': 'EQUITY', 'underlying': 'RELIANCE'})
        self.assertEqual(res, 'RELIANCE')

    def test_resolve_future_mcx_mini(self):
        # Should prefer MINI
        res = self.resolver.resolve({'type': 'FUT', 'underlying': 'SILVER', 'exchange': 'MCX'})
        self.assertIn('SILVERMIC', res)

    def test_resolve_future_nse(self):
        res = self.resolver.resolve({'type': 'FUT', 'underlying': 'NIFTY'})
        self.assertEqual(res, 'NIFTY23OCTFUT')

    def test_resolve_option_weekly(self):
        # Should pick nearest expiry (Weekly)
        res = self.resolver.resolve({'type': 'OPT', 'underlying': 'NIFTY', 'expiry_preference': 'WEEKLY', 'option_type': 'CE'})
        # Validation returns a dict
        self.assertEqual(res['status'], 'valid')
        # Check that it picked the nearer date
        expiry_dt = datetime.strptime(res['expiry'], '%Y-%m-%d')
        self.assertTrue((expiry_dt - datetime.now()).days < 30)
        # Verify it picked d1 not d2
        expected = (datetime.now() + timedelta(days=self.d1)).strftime('%Y-%m-%d')
        self.assertEqual(res['expiry'], expected)

    def test_resolve_option_monthly(self):
        res = self.resolver.resolve({'type': 'OPT', 'underlying': 'NIFTY', 'expiry_preference': 'MONTHLY', 'option_type': 'CE'})
        self.assertEqual(res['status'], 'valid')
        # Should pick the one 10 days away (Last in Oct) not 3 days (Nearest) or Nov (Next month)
        self.assertIn('MONTHLY', res['sample_symbol'])

if __name__ == '__main__':
    unittest.main()
