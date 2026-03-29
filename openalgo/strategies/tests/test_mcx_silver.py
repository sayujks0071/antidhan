import os
import sys
import unittest
import pandas as pd
import numpy as np

# Add scripts directory to path to find the strategy
current_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(current_dir)
scripts_dir = os.path.join(strategies_dir, "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

# Add openalgo directory to path so 'import utils' works (for trading_utils)
openalgo_dir = os.path.dirname(strategies_dir)
if openalgo_dir not in sys.path:
    sys.path.insert(0, openalgo_dir)

# Import strategy
try:
    import mcx_silver_momentum
    from mcx_silver_momentum import MCXSilverMomentumStrategy
except ImportError:
    # If scripts_dir didn't work for some reason (e.g. running from different cwd)
    sys.path.append("openalgo/strategies/scripts")
    import mcx_silver_momentum
    from mcx_silver_momentum import MCXSilverMomentumStrategy

class TestMCXSilverMomentum(unittest.TestCase):
    def setUp(self):
        # Setup dummy strategy instance
        self.strategy = MCXSilverMomentumStrategy(
            symbol="SILVERM",
            quantity=1,
            ignore_time=True,
            api_key="TEST"
        )
        # Mock logger to suppress output
        self.strategy.logger.handlers = []

    def test_import(self):
        self.assertTrue('mcx_silver_momentum' in sys.modules)

    def test_generate_signal_buy(self):
        # Create dummy data for Buy Signal: Close > SMA50 and RSI > 55
        # SMA 50 calculation requires 50 periods.
        prices = [100 + i for i in range(60)] # Rising trend
        data = {
            "close": prices,
            "high": [p + 2 for p in prices],
            "low": [p - 2 for p in prices],
            "open": prices,
            "volume": [1000] * 60
        }
        df = pd.DataFrame(data)

        # We need to calculate indicators because generate_signal expects them
        # BaseStrategy calculates them in default_cycle, but here we test generate_signal directly.
        # So we must call calculate_indicators first.
        df = self.strategy.calculate_indicators(df)

        signal = self.strategy.generate_signal(df)
        self.assertEqual(signal, "BUY")

    def test_generate_signal_sell(self):
        # Create dummy data for Sell Signal: Close < SMA50 and RSI < 45
        # Falling trend
        prices = [200 - i for i in range(60)]
        data = {
            "close": prices,
            "high": [p + 2 for p in prices],
            "low": [p - 2 for p in prices],
            "open": prices,
            "volume": [1000] * 60
        }
        df = pd.DataFrame(data)

        # Calculate indicators
        df = self.strategy.calculate_indicators(df)

        signal = self.strategy.generate_signal(df)
        self.assertEqual(signal, "SELL")

if __name__ == '__main__':
    unittest.main()
