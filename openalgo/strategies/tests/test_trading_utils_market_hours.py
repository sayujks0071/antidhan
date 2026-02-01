import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock
import sys
import os
import pytz

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from openalgo.strategies.utils.trading_utils import is_market_open, is_mcx_market_open

class TestMarketHours(unittest.TestCase):
    @patch('openalgo.strategies.utils.trading_utils.datetime')
    def test_nse_hours(self, mock_datetime):
        ist = pytz.timezone('Asia/Kolkata')

        # Weekday 10:00 AM (Open)
        mock_now = datetime(2023, 10, 25, 10, 0, 0, tzinfo=ist) # Wednesday
        mock_datetime.now.return_value = mock_now
        self.assertTrue(is_market_open("NSE"))
        self.assertTrue(is_market_open()) # Default

        # Weekday 9:00 AM (Closed)
        mock_now = datetime(2023, 10, 25, 9, 0, 0, tzinfo=ist)
        mock_datetime.now.return_value = mock_now
        self.assertFalse(is_market_open("NSE"))

        # Weekend (Closed)
        mock_now = datetime(2023, 10, 28, 10, 0, 0, tzinfo=ist) # Saturday
        mock_datetime.now.return_value = mock_now
        self.assertFalse(is_market_open("NSE"))

    @patch('openalgo.strategies.utils.trading_utils.datetime')
    def test_mcx_hours(self, mock_datetime):
        ist = pytz.timezone('Asia/Kolkata')

        # Weekday 10:00 AM (Open)
        mock_now = datetime(2023, 10, 25, 10, 0, 0, tzinfo=ist)
        mock_datetime.now.return_value = mock_now
        self.assertTrue(is_mcx_market_open())
        self.assertTrue(is_market_open("MCX"))

        # Weekday 9:05 AM (Open for MCX, Closed for NSE)
        mock_now = datetime(2023, 10, 25, 9, 5, 0, tzinfo=ist)
        mock_datetime.now.return_value = mock_now
        self.assertTrue(is_mcx_market_open())
        self.assertTrue(is_market_open("MCX"))
        self.assertFalse(is_market_open("NSE"))

        # Weekday 23:00 (Open for MCX)
        mock_now = datetime(2023, 10, 25, 23, 0, 0, tzinfo=ist)
        mock_datetime.now.return_value = mock_now
        self.assertTrue(is_mcx_market_open())
        self.assertTrue(is_market_open("MCX"))

        # Weekday 23:45 (Closed for MCX)
        mock_now = datetime(2023, 10, 25, 23, 45, 0, tzinfo=ist)
        mock_datetime.now.return_value = mock_now
        self.assertFalse(is_mcx_market_open())
        self.assertFalse(is_market_open("MCX"))

        # Weekend (Closed)
        mock_now = datetime(2023, 10, 28, 10, 0, 0, tzinfo=ist)
        mock_datetime.now.return_value = mock_now
        self.assertFalse(is_mcx_market_open())

if __name__ == '__main__':
    unittest.main()
