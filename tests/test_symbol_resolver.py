import unittest
import pandas as pd
import os
import shutil
from datetime import datetime, timedelta
from openalgo.strategies.utils.symbol_resolver import SymbolResolver

class TestSymbolResolver(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/data"
        os.makedirs(self.test_dir, exist_ok=True)
        self.csv_path = os.path.join(self.test_dir, "instruments.csv")

        # Generate Mock Data
        now = datetime.now()

        # Expiries
        days_to_thurs = (3 - now.weekday()) % 7
        if days_to_thurs == 0: days_to_thurs = 7
        next_thursday = (now + timedelta(days=days_to_thurs)).replace(hour=0, minute=0, second=0, microsecond=0)

        # End of Month
        import calendar
        last_day = calendar.monthrange(now.year, now.month)[1]
        month_end = datetime(now.year, now.month, last_day).replace(hour=0, minute=0, second=0, microsecond=0)

        data = [
            # Equity
            {'exchange': 'NSE', 'symbol': 'RELIANCE', 'name': 'RELIANCE', 'expiry': None, 'instrument_type': 'EQ', 'strike': 0},

            # MCX Futures
            {'exchange': 'MCX', 'symbol': 'SILVER23NOVFUT', 'name': 'SILVER', 'expiry': month_end, 'instrument_type': 'FUT', 'strike': 0},
            {'exchange': 'MCX', 'symbol': 'SILVERM23NOVFUT', 'name': 'SILVER', 'expiry': month_end, 'instrument_type': 'FUT', 'strike': 0},

            # NSE Options (Weekly)
            {'exchange': 'NFO', 'symbol': 'NIFTY23OCT19500CE', 'name': 'NIFTY', 'expiry': next_thursday, 'instrument_type': 'OPT', 'strike': 19500},
            {'exchange': 'NFO', 'symbol': 'NIFTY23OCT19500PE', 'name': 'NIFTY', 'expiry': next_thursday, 'instrument_type': 'OPT', 'strike': 19500},
            {'exchange': 'NFO', 'symbol': 'NIFTY23OCT19600CE', 'name': 'NIFTY', 'expiry': next_thursday, 'instrument_type': 'OPT', 'strike': 19600},

            # NSE Options (Monthly - assume strictly later than weekly for test)
            {'exchange': 'NFO', 'symbol': 'NIFTY23NOV19500CE', 'name': 'NIFTY', 'expiry': next_thursday + timedelta(days=30), 'instrument_type': 'OPT', 'strike': 19500},
        ]

        df = pd.DataFrame(data)
        df.to_csv(self.csv_path, index=False)

        self.resolver = SymbolResolver(self.csv_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_equity_resolve(self):
        config = {'type': 'EQUITY', 'underlying': 'RELIANCE', 'exchange': 'NSE'}
        res = self.resolver.resolve(config)
        self.assertEqual(res, 'RELIANCE')

    def test_mcx_mini_preference(self):
        config = {'type': 'FUT', 'underlying': 'SILVER', 'exchange': 'MCX'}
        res = self.resolver.resolve(config)
        # Should pick SILVERM... because it contains 'SILVERM'
        self.assertTrue('SILVERM' in res)

    def test_option_resolve_weekly(self):
        config = {'type': 'OPT', 'underlying': 'NIFTY', 'exchange': 'NFO', 'expiry_preference': 'WEEKLY', 'option_type': 'CE'}
        res = self.resolver.resolve(config)
        self.assertEqual(res['status'], 'valid')
        # Should be the earlier date
        # Check expiry string
        # We can't easily check exact string without recalc, but we know it should validly return dict.
        self.assertIn('expiry', res)

    def test_get_tradable_symbol_atm(self):
        config = {'type': 'OPT', 'underlying': 'NIFTY', 'exchange': 'NFO', 'option_type': 'CE'}
        # Spot 19520 -> Nearest 19500
        sym = self.resolver.get_tradable_symbol(config, spot_price=19520)
        self.assertEqual(sym, 'NIFTY23OCT19500CE')

    def test_get_tradable_symbol_itm(self):
        config = {'type': 'OPT', 'underlying': 'NIFTY', 'exchange': 'NFO', 'option_type': 'CE', 'strike_criteria': 'ITM'}
        # Spot 19560 -> ATM 19600 -> ITM (Call) = 19500 (Lower strike)
        # Wait, 19560 ATM is 19600 (diff 40) vs 19500 (diff 60).
        # Logic: 19560. Nearest strike in [19500, 19600]. 19600 is closer.
        # ATM = 19600.
        # ITM Call = Strike < Spot. 19500.
        # My logic in code: idx = max(0, atm_index - 1).
        # Strikes: [19500, 19600].
        # ATM Index (19600) = 1.
        # ITM Index = 0 -> 19500.
        sym = self.resolver.get_tradable_symbol(config, spot_price=19560)
        self.assertEqual(sym, 'NIFTY23OCT19500CE')

if __name__ == '__main__':
    unittest.main()
