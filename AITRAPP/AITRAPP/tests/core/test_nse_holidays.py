import json
import os
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, date

from packages.core.nse_holidays import (
    extract_segment_dates,
    fetch_nse_holidays,
    save_cache,
    load_cache,
    get_trading_holidays
)

class TestNSEHolidays(unittest.TestCase):

    def setUp(self):
        self.sample_payload = {
            "FO": [
                {"tradingDate": "26-Jan-2026", "weekDay": "Monday", "description": "Republic Day"},
                {"tradingDate": "15-Feb-2026", "weekDay": "Sunday", "description": "Mahashivratri"}
            ],
            "CM": [
                {"tradingDate": "01-Jan-2026", "weekDay": "Thursday", "description": "New year"}
            ]
        }
        self.test_cache_path = "test_nse_cache.json"

    def tearDown(self):
        if os.path.exists(self.test_cache_path):
            os.remove(self.test_cache_path)

    def test_extract_segment_dates(self):
        # Test FO segment extraction
        dates = extract_segment_dates(self.sample_payload, "FO")
        expected = {"2026-01-26", "2026-02-15"}
        self.assertEqual(dates, expected)

        # Test CM segment extraction
        dates = extract_segment_dates(self.sample_payload, "CM")
        expected = {"2026-01-01"}
        self.assertEqual(dates, expected)

        # Test missing segment
        dates = extract_segment_dates(self.sample_payload, "MISSING")
        self.assertEqual(dates, set())

        # Test invalid date handling
        bad_payload = {"FO": [{"tradingDate": "Invalid-Date"}]}
        dates = extract_segment_dates(bad_payload, "FO")
        self.assertEqual(dates, set())

    @patch('requests.Session')
    def test_fetch_nse_holidays_success(self, mock_session):
        # Setup mock
        mock_response = MagicMock()
        mock_response.json.return_value = self.sample_payload
        mock_response.raise_for_status.return_value = None

        session_instance = mock_session.return_value
        session_instance.get.return_value = mock_response

        # Test fetch
        result = fetch_nse_holidays(retries=0)
        self.assertEqual(result, self.sample_payload)

        # Verify warm-up call and data call
        self.assertEqual(session_instance.get.call_count, 2)

    @patch('requests.Session')
    def test_fetch_nse_holidays_failure(self, mock_session):
        # Setup mock to raise exception
        session_instance = mock_session.return_value
        session_instance.get.side_effect = Exception("Network Error")

        # Test fetch
        result = fetch_nse_holidays(retries=1)
        self.assertIsNone(result)

        # Verify retries
        self.assertTrue(session_instance.get.call_count >= 2)

    def test_save_and_load_cache(self):
        save_cache(self.sample_payload, self.test_cache_path)
        self.assertTrue(os.path.exists(self.test_cache_path))

        loaded = load_cache(self.test_cache_path)
        self.assertEqual(loaded, self.sample_payload)

    @patch('packages.core.nse_holidays.fetch_nse_holidays')
    def test_get_trading_holidays_fresh_cache(self, mock_fetch):
        # Create a fresh cache file
        save_cache(self.sample_payload, self.test_cache_path)

        # Call
        holidays = get_trading_holidays(cache_path=self.test_cache_path, refresh_days=1)

        # Verify no network call
        mock_fetch.assert_not_called()
        self.assertEqual(holidays, {"2026-01-26", "2026-02-15"})

    @patch('packages.core.nse_holidays.fetch_nse_holidays')
    def test_get_trading_holidays_stale_cache_refresh_success(self, mock_fetch):
        # Create a stale cache file
        save_cache(self.sample_payload, self.test_cache_path)
        # Set mtime to 10 days ago
        past_time = datetime.now().timestamp() - (10 * 24 * 3600)
        os.utime(self.test_cache_path, (past_time, past_time))

        # Setup mock to return new data
        new_payload = {"FO": [{"tradingDate": "01-Jan-2027"}]}
        mock_fetch.return_value = new_payload

        # Call
        holidays = get_trading_holidays(cache_path=self.test_cache_path, refresh_days=5, allow_network=True)

        # Verify network call and new data
        mock_fetch.assert_called_once()
        self.assertEqual(holidays, {"2027-01-01"})

        # Verify cache file updated
        loaded = load_cache(self.test_cache_path)
        self.assertEqual(loaded, new_payload)

    @patch('packages.core.nse_holidays.fetch_nse_holidays')
    def test_get_trading_holidays_stale_cache_refresh_failure(self, mock_fetch):
        # Create a stale cache file
        save_cache(self.sample_payload, self.test_cache_path)
        past_time = datetime.now().timestamp() - (10 * 24 * 3600)
        os.utime(self.test_cache_path, (past_time, past_time))

        # Setup mock to fail
        mock_fetch.return_value = None

        # Call
        holidays = get_trading_holidays(cache_path=self.test_cache_path, refresh_days=5, allow_network=True)

        # Verify network call and fallback to stale data
        mock_fetch.assert_called_once()
        self.assertEqual(holidays, {"2026-01-26", "2026-02-15"})

    @patch('packages.core.nse_holidays.fetch_nse_holidays')
    def test_get_trading_holidays_no_cache_fallback_seed(self, mock_fetch):
        # Ensure no cache file
        if os.path.exists(self.test_cache_path):
            os.remove(self.test_cache_path)

        # Mock fetch failure
        mock_fetch.return_value = None

        # Call (will use seed file from packages/core/data/nse_holidays_trading.json)
        holidays = get_trading_holidays(cache_path=self.test_cache_path, allow_network=True)

        # The seed file has 2026 dates (we added them in the previous steps)
        self.assertIn("2026-01-26", holidays)

        # And it should have created the cache file from the seed
        self.assertTrue(os.path.exists(self.test_cache_path))

if __name__ == '__main__':
    unittest.main()
