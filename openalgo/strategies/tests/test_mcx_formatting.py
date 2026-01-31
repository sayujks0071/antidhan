import unittest
from datetime import date
import sys
import os

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Try importing with full package path
try:
    from openalgo.strategies.utils.mcx_utils import format_mcx_symbol, normalize_mcx_string
except ImportError:
    # Fallback to relative if package structure is not fully intact in environment
    sys.path.insert(0, os.path.join(repo_root, 'openalgo', 'strategies', 'utils'))
    from mcx_utils import format_mcx_symbol, normalize_mcx_string

class TestMCXFormatting(unittest.TestCase):
    def test_gold_mini(self):
        # GOLDM05FEB26FUT for date(2026,2,5) with mini=True
        # Expect: GOLD + M + 05 + FEB + 26 + FUT
        result = format_mcx_symbol("GOLD", date(2026, 2, 5), mini=True)
        self.assertEqual(result, "GOLDM05FEB26FUT")

    def test_silver_mini(self):
        # SILVERM27FEB26FUT for date(2026,2,27) with mini=True
        result = format_mcx_symbol("SILVER", date(2026, 2, 27), mini=True)
        self.assertEqual(result, "SILVERM27FEB26FUT")

    def test_crudeoil_standard(self):
        # CRUDEOIL19FEB26FUT for date(2026,2,19) with mini=False
        result = format_mcx_symbol("CRUDEOIL", date(2026, 2, 19), mini=False)
        self.assertEqual(result, "CRUDEOIL19FEB26FUT")

    def test_zero_padding(self):
        # Test DD zero padding
        # 5th -> 05
        result = format_mcx_symbol("TEST", date(2026, 1, 5), mini=False)
        self.assertEqual(result, "TEST05JAN26FUT")

        # 15th -> 15
        result = format_mcx_symbol("TEST", date(2026, 1, 15), mini=False)
        self.assertEqual(result, "TEST15JAN26FUT")

    def test_month_uppercase(self):
        # Test MMM uppercase mapping
        # date(2026, 2, 5) -> FEB
        result = format_mcx_symbol("TEST", date(2026, 2, 5), mini=False)
        self.assertIn("FEB", result)

    def test_year_format(self):
        # YY correct
        result = format_mcx_symbol("TEST", date(2026, 1, 1), mini=False)
        self.assertTrue(result.endswith("26FUT"))

    def test_normalization_logic(self):
        # Test normalization of malformed strings
        # Case 1: Single digit day
        self.assertEqual(normalize_mcx_string("GOLDM5FEB26FUT"), "GOLDM05FEB26FUT")
        # Case 2: Lowercase
        self.assertEqual(normalize_mcx_string("goldm05feb26fut"), "GOLDM05FEB26FUT")
        # Case 3: Mixed case
        self.assertEqual(normalize_mcx_string("SiLvErM27fEb26FuT"), "SILVERM27FEB26FUT")
        # Case 4: Already valid
        self.assertEqual(normalize_mcx_string("GOLDM05FEB26FUT"), "GOLDM05FEB26FUT")

if __name__ == '__main__':
    unittest.main()
