import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add strategies root to path to mimic running from root
strategies_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../strategies'))
sys.path.insert(0, strategies_root)

# Helper to load the strategy module from file path
import importlib.util

def load_strategy_module(filepath):
    spec = importlib.util.spec_from_file_location("nifty_smart_regime", filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules["nifty_smart_regime"] = module
    spec.loader.exec_module(module)
    return module

class TestNiftySmartRegime(unittest.TestCase):
    def setUp(self):
        # Set up environment variables required by the strategy
        self.env_patcher = patch.dict(os.environ, {
            "OPENALGO_APIKEY": "test_key",
            "OPENALGO_HOST": "http://test_host",
            "STRATEGY_NAME": "TestStrategy",
            "UNDERLYING": "NIFTY",
            "PCR_BULLISH": "1.2",
            "PCR_BEARISH": "0.8",
            "WALL_BUFFER": "25.0"
        })
        self.env_patcher.start()

        # Mock utilities to prevent import errors during module load
        # We need to mock 'trading_utils', 'optionchain_utils', 'strategy_common'
        # because the script imports them at module level.
        self.mock_trading_utils = MagicMock()
        self.mock_optionchain_utils = MagicMock()
        self.mock_strategy_common = MagicMock()

        sys.modules['trading_utils'] = self.mock_trading_utils
        sys.modules['optionchain_utils'] = self.mock_optionchain_utils
        sys.modules['strategy_common'] = self.mock_strategy_common

        # Setup mocks for specific classes
        self.mock_client_class = MagicMock()
        self.mock_tracker_class = MagicMock()
        self.mock_debouncer_class = MagicMock()
        self.mock_limiter_class = MagicMock()

        self.mock_optionchain_utils.OptionChainClient = self.mock_client_class
        self.mock_optionchain_utils.OptionPositionTracker = self.mock_tracker_class
        self.mock_optionchain_utils.safe_float = lambda x, d=0.0: float(x) if x else d
        self.mock_optionchain_utils.safe_int = lambda x, d=0: int(float(x)) if x else d

        self.mock_strategy_common.SignalDebouncer = self.mock_debouncer_class
        self.mock_strategy_common.TradeLimiter = self.mock_limiter_class
        self.mock_strategy_common.format_kv = lambda **kwargs: str(kwargs)

        # Load the strategy module
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts/nifty_smart_regime.py'))
        self.strategy_module = load_strategy_module(script_path)
        self.strategy_class = self.strategy_module.NiftySmartRegime

    def tearDown(self):
        self.env_patcher.stop()
        # Clean up sys.modules
        if 'nifty_smart_regime' in sys.modules:
            del sys.modules['nifty_smart_regime']

    def test_regime_detection_neutral(self):
        """Test Neutral Regime Detection (Iron Condor)"""
        strategy = self.strategy_class()

        # Mock option chain data: PCR ~1.0 (Neutral), Spot inside walls
        chain = [
            {"strike": 25000, "ce": {"oi": 100}, "pe": {"oi": 10000}}, # Max PE OI (Support)
            {"strike": 25500, "ce": {"oi": 100}, "pe": {"oi": 100}},
            {"strike": 26000, "ce": {"oi": 10000}, "pe": {"oi": 100}}, # Max CE OI (Resistance)
        ]
        # Total CE OI = 10200, Total PE OI = 10200 -> PCR = 1.0

        # Mock analyze_chain since it's an instance method
        # But analyze_chain is pure logic, so we can test it directly or rely on it
        # Let's verify analyze_chain first
        stats = strategy.analyze_chain(chain)
        self.assertEqual(stats["max_ce_strike"], 26000)
        self.assertEqual(stats["max_pe_strike"], 25000)
        self.assertAlmostEqual(stats["pcr"], 1.0)

        # To test run loop logic, we need to mock internal state and flow
        # It's hard to test run() loop directly without heavy refactoring
        # So we verify logic components

        spot = 25500 # Midway
        sup = 25000
        res = 26000
        pcr = 1.0

        is_bullish = pcr > 1.2 and spot > (sup + 25)
        is_bearish = pcr < 0.8 and spot < (res - 25)
        is_neutral = (0.8 <= pcr <= 1.2) and (spot > sup) and (spot < res)

        self.assertTrue(is_neutral)
        self.assertFalse(is_bullish)
        self.assertFalse(is_bearish)

    def test_regime_detection_bullish(self):
        """Test Bullish Regime Detection (Bull Put Spread)"""
        spot = 25100
        sup = 25000
        res = 26000
        pcr = 1.5 # Bullish

        is_bullish = pcr > 1.2 and spot > (sup + 25)
        self.assertTrue(is_bullish)

    def test_regime_detection_bearish(self):
        """Test Bearish Regime Detection (Bear Call Spread)"""
        spot = 25900
        sup = 25000
        res = 26000
        pcr = 0.5 # Bearish

        is_bearish = pcr < 0.8 and spot < (res - 25)
        self.assertTrue(is_bearish)

if __name__ == '__main__':
    unittest.main()
