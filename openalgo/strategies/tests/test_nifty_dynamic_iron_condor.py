import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import importlib.util

# Helper to load the strategy module dynamically
def load_strategy_module():
    # Path to the strategy script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    strategy_path = os.path.join(current_dir, '../scripts/nifty_dynamic_iron_condor.py')

    # We need to mock the imports that the strategy does
    # The strategy imports from 'trading_utils', 'optionchain_utils', 'strategy_common'
    # We should make sure these are importable or mocked

    spec = importlib.util.spec_from_file_location("nifty_dynamic_iron_condor", strategy_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["nifty_dynamic_iron_condor"] = module

    # We need to patch sys.path so it can find utils?
    # The script does it itself, so we might just let it run.
    # However, we want to mock the API calls.

    with patch.dict(os.environ, {
        "OPENALGO_APIKEY": "test_key",
        "OPENALGO_HOST": "http://test_host",
        "STRATEGY_NAME": "TestStrategy"
    }):
        spec.loader.exec_module(module)

    return module

class TestNiftyDynamicIronCondor(unittest.TestCase):
    def setUp(self):
        # Load module
        self.module = load_strategy_module()
        self.StrategyClass = self.module.NiftyDynamicIronCondorStrategy
        self.NetCreditTracker = self.module.NetCreditTracker

    def test_tracker_pnl_calculation(self):
        # Setup Tracker
        tracker = self.NetCreditTracker(sl_pct=40.0, tp_pct=50.0, max_hold_min=45)

        # Simulate Entry: Iron Condor (Sell 100+100, Buy 20+20)
        # Net Credit = 200 - 40 = 160
        legs = [
            {"symbol": "CE_SELL", "action": "SELL", "quantity": 1},
            {"symbol": "PE_SELL", "action": "SELL", "quantity": 1},
            {"symbol": "CE_BUY", "action": "BUY", "quantity": 1},
            {"symbol": "PE_BUY", "action": "BUY", "quantity": 1},
        ]
        entry_prices = [100.0, 100.0, 20.0, 20.0]
        tracker.add_legs(legs, entry_prices, side="SELL")

        # Test 1: No PnL Change
        chain = [
            {"ce": {"symbol": "CE_SELL", "ltp": 100.0}, "pe": {}},
            {"pe": {"symbol": "PE_SELL", "ltp": 100.0}, "ce": {}},
            {"ce": {"symbol": "CE_BUY", "ltp": 20.0}, "pe": {}},
            {"pe": {"symbol": "PE_BUY", "ltp": 20.0}, "ce": {}},
        ]
        exit_now, _, _ = tracker.should_exit(chain)
        self.assertFalse(exit_now)

        # Test 2: Profit (Premium Decay)
        # Current: Sell legs 50+50=100, Buy legs 10+10=20.
        # Cost to Close = 100 - 20 = 80.
        # Net Credit = 160.
        # PnL = 160 - 80 = +80.
        # PnL% = (80 / 160) * 100 = 50%.
        # TP is 50%. Should exit.
        chain_profit = [
            {"ce": {"symbol": "CE_SELL", "ltp": 50.0}, "pe": {}},
            {"pe": {"symbol": "PE_SELL", "ltp": 50.0}, "ce": {}},
            {"ce": {"symbol": "CE_BUY", "ltp": 10.0}, "pe": {}},
            {"pe": {"symbol": "PE_BUY", "ltp": 10.0}, "ce": {}},
        ]
        exit_now, _, reason = tracker.should_exit(chain_profit)
        self.assertTrue(exit_now)
        self.assertIn("take_profit", reason)

        # Test 3: Loss (Premium Spike)
        # Current: Sell legs 150+150=300, Buy legs 30+30=60.
        # Cost to Close = 300 - 60 = 240.
        # Net Credit = 160.
        # PnL = 160 - 240 = -80.
        # PnL% = (-80 / 160) * 100 = -50%.
        # SL is 40%. Should exit.
        chain_loss = [
            {"ce": {"symbol": "CE_SELL", "ltp": 150.0}, "pe": {}},
            {"pe": {"symbol": "PE_SELL", "ltp": 150.0}, "ce": {}},
            {"ce": {"symbol": "CE_BUY", "ltp": 30.0}, "pe": {}},
            {"pe": {"symbol": "PE_BUY", "ltp": 30.0}, "ce": {}},
        ]
        exit_now, _, reason = tracker.should_exit(chain_loss)
        self.assertTrue(exit_now)
        self.assertIn("stop_loss", reason)

    @patch('time.time')
    @patch('time.sleep')
    def test_strategy_regime(self, mock_sleep, mock_time):
        strategy = self.StrategyClass()

        # 1. Bullish Case
        # PCR > 1.1 (1.5) and Price > EMA (105 > 100)
        strategy.current_ema = 100.0
        regime = strategy.determine_regime(pcr=1.5, spot=105.0)
        self.assertEqual(regime, "BULLISH")

        # 2. Bearish Case
        # PCR < 0.8 (0.6) and Price < EMA (95 < 100)
        strategy.current_ema = 100.0
        regime = strategy.determine_regime(pcr=0.6, spot=95.0)
        self.assertEqual(regime, "BEARISH")

        # 3. Neutral Case
        # Mixed: PCR Bullish (1.5) but Price Bearish (95 < 100)
        regime = strategy.determine_regime(pcr=1.5, spot=95.0)
        self.assertEqual(regime, "NEUTRAL")

        # PCR Neutral (1.0)
        regime = strategy.determine_regime(pcr=1.0, spot=100.0)
        self.assertEqual(regime, "NEUTRAL")

    def test_calculate_pcr(self):
        strategy = self.StrategyClass()
        chain = [
            {"ce": {"oi": 1000}, "pe": {"oi": 500}}, # 0.5
            {"ce": {"oi": 2000}, "pe": {"oi": 4000}}, # 2.0
        ]
        # Total CE = 3000, Total PE = 4500. PCR = 1.5
        pcr = strategy.calculate_pcr(chain)
        self.assertEqual(pcr, 1.5)

if __name__ == '__main__':
    unittest.main()
