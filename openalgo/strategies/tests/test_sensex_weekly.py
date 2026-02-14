import unittest
import sys
import os

# Set dummy API key to pass the check in the strategy module
os.environ["OPENALGO_APIKEY"] = "dummy_key"

# Adjust path to include strategy directory so we can import the strategy class
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sensex_weekly_income_v2 import NetCreditPositionTracker

class TestSensexWeekly(unittest.TestCase):
    def test_net_credit_tracker_loss(self):
        # Setup: Iron Condor
        # Sell OTM2 @ 100
        # Sell OTM2 @ 100
        # Buy OTM4 @ 20
        # Buy OTM4 @ 20
        # Net Credit = 200 - 40 = 160.

        tracker = NetCreditPositionTracker(sl_pct=35.0, tp_pct=45.0, max_hold_min=60)

        legs = [
            {"symbol": "SENSEX_CE_SELL", "action": "SELL", "quantity": 1},
            {"symbol": "SENSEX_PE_SELL", "action": "SELL", "quantity": 1},
            {"symbol": "SENSEX_CE_BUY", "action": "BUY", "quantity": 1},
            {"symbol": "SENSEX_PE_BUY", "action": "BUY", "quantity": 1},
        ]
        entry_prices = [100.0, 100.0, 20.0, 20.0]

        tracker.add_legs(legs, entry_prices, side="SELL")

        # Scenario: Market moves against us.
        # Short legs increase to 120. Long legs decrease to 10 (theta decay or delta).
        # Cost to close: (120 * 1) + (120 * 1) - (10 * 1) - (10 * 1) = 240 - 20 = 220.
        # PnL = Net Credit (160) - Cost to Close (220) = -60.
        # PnL % = -60 / 160 = -37.5%.
        # SL is 35%. Should exit.

        chain = [
            {"ce": {"symbol": "SENSEX_CE_SELL", "ltp": 120.0}, "pe": {}},
            {"pe": {"symbol": "SENSEX_PE_SELL", "ltp": 120.0}, "ce": {}},
            {"ce": {"symbol": "SENSEX_CE_BUY", "ltp": 10.0}, "pe": {}},
            {"pe": {"symbol": "SENSEX_PE_BUY", "ltp": 10.0}, "ce": {}},
        ]

        should_exit, _, reason = tracker.should_exit(chain)
        self.assertTrue(should_exit)
        self.assertIn("stop_loss", reason)
        self.assertIn("-37.5%", reason)

    def test_net_credit_tracker_profit(self):
        # Setup: Iron Condor
        # Net Credit = 160.
        tracker = NetCreditPositionTracker(sl_pct=35.0, tp_pct=45.0, max_hold_min=60)

        legs = [
            {"symbol": "SENSEX_CE_SELL", "action": "SELL", "quantity": 1},
            {"symbol": "SENSEX_PE_SELL", "action": "SELL", "quantity": 1},
            {"symbol": "SENSEX_CE_BUY", "action": "BUY", "quantity": 1},
            {"symbol": "SENSEX_PE_BUY", "action": "BUY", "quantity": 1},
        ]
        entry_prices = [100.0, 100.0, 20.0, 20.0]
        tracker.add_legs(legs, entry_prices, side="SELL")

        # Scenario: Theta decay works.
        # Short legs decrease to 50. Long legs decrease to 5.
        # Cost to close: 50 + 50 - 5 - 5 = 90.
        # PnL = 160 - 90 = 70.
        # PnL % = 70 / 160 = 43.75%.
        # TP is 45%. Should NOT exit yet (close but not quite).

        chain = [
            {"ce": {"symbol": "SENSEX_CE_SELL", "ltp": 50.0}, "pe": {}},
            {"pe": {"symbol": "SENSEX_PE_SELL", "ltp": 50.0}, "ce": {}},
            {"ce": {"symbol": "SENSEX_CE_BUY", "ltp": 5.0}, "pe": {}},
            {"pe": {"symbol": "SENSEX_PE_BUY", "ltp": 5.0}, "ce": {}},
        ]
        should_exit, _, reason = tracker.should_exit(chain)
        self.assertFalse(should_exit)

        # Scenario: Further decay.
        # Short legs to 40. Longs to 2.
        # Cost to close: 80 - 4 = 76.
        # PnL = 160 - 76 = 84.
        # PnL % = 84 / 160 = 52.5%.
        # TP is 45%. Should exit.

        chain = [
            {"ce": {"symbol": "SENSEX_CE_SELL", "ltp": 40.0}, "pe": {}},
            {"pe": {"symbol": "SENSEX_PE_SELL", "ltp": 40.0}, "ce": {}},
            {"ce": {"symbol": "SENSEX_CE_BUY", "ltp": 2.0}, "pe": {}},
            {"pe": {"symbol": "SENSEX_PE_BUY", "ltp": 2.0}, "ce": {}},
        ]
        should_exit, _, reason = tracker.should_exit(chain)
        self.assertTrue(should_exit)
        self.assertIn("take_profit", reason)
        self.assertIn("52.5%", reason)

if __name__ == '__main__':
    unittest.main()
