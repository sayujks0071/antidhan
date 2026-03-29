import unittest
import pandas as pd
import numpy as np
import sys
import os
from unittest.mock import MagicMock

# Add path to strategies
current_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.join(os.path.dirname(current_dir), "openalgo", "strategies", "scripts")
utils_dir = os.path.join(os.path.dirname(current_dir), "openalgo", "strategies", "utils")
sys.path.insert(0, strategies_dir)
sys.path.insert(0, utils_dir)

# Import the strategy
# Since the strategy file is in strategies/scripts, we need to import it carefully
# We can use importlib or just regular import if path is correct
try:
    import mcx_silver_smart_momentum_strategy as strategy
except ImportError:
    # Try alternate path
    sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'scripts'))
    import mcx_silver_smart_momentum_strategy as strategy

class TestMCXSilverSmartMomentum(unittest.TestCase):
    def setUp(self):
        # Create dummy data
        self.dates = pd.date_range(start="2024-01-01", periods=100, freq="15min")
        self.df = pd.DataFrame({
            "open": np.random.rand(100) * 100,
            "high": np.random.rand(100) * 100,
            "low": np.random.rand(100) * 100,
            "close": np.random.rand(100) * 100,
            "volume": np.random.randint(100, 1000, 100)
        }, index=self.dates)

        # Make data suitable for BUY signal (Close > EMA, RSI > 55)
        # We need to manipulate the last few candles to ensure EMA and RSI are in range

        # Calculate EMA manually to guide values
        # Let's just force the values for the last candle in the test

    def test_indicators_calculation(self):
        """Test that indicators are added to the dataframe"""
        strat = strategy.MCXStrategy("TEST", "key", "host", {})
        strat.data = self.df.copy()
        strat.calculate_indicators()

        self.assertIn("rsi", strat.data.columns)
        self.assertIn("atr", strat.data.columns)
        self.assertIn("ema", strat.data.columns)

    def test_buy_signal(self):
        """Test BUY signal generation"""
        # Create a trend where price is rising
        prices = np.linspace(100, 150, 100) # Uptrend
        df = pd.DataFrame({
            "open": prices,
            "high": prices + 1,
            "low": prices - 1,
            "close": prices,
            "volume": 1000
        }, index=self.dates)

        # This should produce RSI > 50 and Close > EMA

        signal, qty, meta = strategy.generate_signal(df)

        # Note: RSI calculation needs some volatility, straight line might result in NaN or flat RSI
        # Let's check what we get
        # If signal is HOLD, it might be due to RSI not being exactly > 55 or data warm up

        # Let's force indicators logic by mocking calculate_indicators if needed,
        # but better to test real calculation.

        # We can inspect the dataframe inside the strategy if we instantiate it manually
        strat = strategy.MCXStrategy("TEST", "key", "host", {})
        strat.data = df.copy()
        strat.calculate_indicators()
        last = strat.data.iloc[-1]

        print(f"DEBUG: Close={last['close']}, EMA={last['ema']}, RSI={last['rsi']}")

        # If RSI is not > 55, we might need to spike it
        if last['rsi'] <= 55:
            # Create a spike
            df.iloc[-1, df.columns.get_loc('close')] = df.iloc[-2]['close'] * 1.05 # 5% jump

        signal, qty, meta = strategy.generate_signal(df)

        # We expect BUY if logic holds
        # Close > EMA (uptrend) and RSI > 55 (jump)
        self.assertEqual(signal, "BUY")

    def test_sell_signal(self):
        """Test SELL signal generation"""
        # Create a trend where price is falling
        prices = np.linspace(150, 100, 100) # Downtrend
        df = pd.DataFrame({
            "open": prices,
            "high": prices + 1,
            "low": prices - 1,
            "close": prices,
            "volume": 1000
        }, index=self.dates)

        # Force a drop at the end to ensure RSI < 45
        df.iloc[-1, df.columns.get_loc('close')] = df.iloc[-2]['close'] * 0.95 # 5% drop

        signal, qty, meta = strategy.generate_signal(df)

        self.assertEqual(signal, "SELL")

if __name__ == "__main__":
    unittest.main()
