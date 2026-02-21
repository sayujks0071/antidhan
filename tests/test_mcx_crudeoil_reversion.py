import sys
import os
import unittest
import pandas as pd
import numpy as np

# Add repo root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the strategy module
# We need to import it using importlib because it is a script, not a package module usually,
# but here it is inside openalgo/strategies/scripts which is package-like.
# However, to be safe and consistent with how scripts are run, we can import it directly.

from openalgo.strategies.scripts.mcx_crudeoil_mean_reversion import generate_signal, MCXStrategy

class TestMCXCrudeOilReversion(unittest.TestCase):
    def setUp(self):
        # Create a basic DataFrame
        self.df_len = 100
        dates = pd.date_range(start="2024-01-01", periods=self.df_len, freq="15min")
        self.df = pd.DataFrame({
            "open": [100.0] * self.df_len,
            "high": [105.0] * self.df_len,
            "low": [95.0] * self.df_len,
            "close": [100.0] * self.df_len,
            "volume": [1000] * self.df_len
        }, index=dates)

    def test_hold_signal(self):
        # Flat market should be HOLD
        signal, confidence, metadata = generate_signal(self.df)
        self.assertEqual(signal, "HOLD")

    def test_buy_signal(self):
        # Simulate a sharp drop to trigger Oversold Mean Reversion
        df = self.df.copy()

        # Create a drop in the last few candles
        # We need enough candles for RSI(14) and BB(20)
        # Drop price significantly in last candle
        df.iloc[-1, df.columns.get_loc("close")] = 80.0
        df.iloc[-1, df.columns.get_loc("low")] = 75.0
        # Also drop previous few to ensure RSI drops
        df.iloc[-2, df.columns.get_loc("close")] = 85.0
        df.iloc[-3, df.columns.get_loc("close")] = 90.0

        # We need to ensure calculate_indicators logic works.
        # Since we are using the actual strategy code, we need to ensure trading_utils imports worked
        # or fallbacks are used. If fallbacks are used, RSI might be 0 or broken.

        # Let's see if we can trigger it.
        # If imports failed in the script, calculate_rsi is lambda s, p: s.
        # If so, rsi will be the price column? No, 's' is the series. So RSI = Price.
        # If Price is 80, RSI=80. Logic: RSI < 30. 80 < 30 is False.
        # So if imports fail, we might not get a signal.

        # Assuming we are running in the repo where trading_utils IS available.
        # The script does: sys.path.insert(0, utils_dir).
        # utils_dir is strategies/utils.

        signal, confidence, metadata = generate_signal(df)

        self.assertEqual(signal, "BUY", "Expected BUY signal for oversold mean reversion")
        self.assertIn("reason", metadata)

    def test_sell_signal(self):
        # Simulate a sharp spike
        df = self.df.copy()
        df.iloc[-1, df.columns.get_loc("close")] = 120.0
        df.iloc[-1, df.columns.get_loc("high")] = 125.0
        df.iloc[-2, df.columns.get_loc("close")] = 115.0
        df.iloc[-3, df.columns.get_loc("close")] = 110.0

        signal, confidence, metadata = generate_signal(df)
        self.assertEqual(signal, "SELL", "Expected SELL signal for overbought mean reversion")
        self.assertIn("reason", metadata)

if __name__ == "__main__":
    unittest.main()
