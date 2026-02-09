import sys
import os
import unittest
import numpy as np
import pandas as pd

# Add repo root to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__)) # openalgo/strategies/tests
strategies_dir = os.path.dirname(current_dir) # openalgo/strategies
scripts_dir = os.path.join(strategies_dir, "scripts") # openalgo/strategies/scripts
repo_root = os.path.dirname(strategies_dir) # openalgo (folder)

sys.path.insert(0, scripts_dir)
sys.path.insert(0, repo_root)

# Verify import
try:
    import mcx_natural_gas_trend
except ImportError:
    # If scripts not in path, try adding it explicitly again or check name
    sys.path.append(scripts_dir)
    import mcx_natural_gas_trend

class TestMCXNaturalGasTrend(unittest.TestCase):
    def setUp(self):
        # Create base dataframe with 100 points
        self.dates = pd.date_range(start='2023-01-01', periods=100, freq='15min')
        self.base_df = pd.DataFrame(index=self.dates)
        self.base_df['high'] = 100
        self.base_df['low'] = 90
        self.base_df['close'] = 95
        self.base_df['volume'] = 1000

    def test_buy_signal(self):
        # Uptrend: SMA20 > SMA50
        # RSI > 55
        # ADX > 25

        df = self.base_df.copy()

        # Create linear uptrend to ensure SMA20 > SMA50
        # Price from 100 to 200
        prices = np.linspace(100, 200, 100)
        df['close'] = prices
        df['high'] = prices + 2
        df['low'] = prices - 2

        # To boost ADX, we need trend strength (high diff between High/Low and prev Close)
        # Linear trend usually has low ADX if volatility is low.
        # Let's inject volatility
        df['high'] = df['close'] + 5
        df['low'] = df['close'] - 5

        # Ensure RSI is high (continuous up moves)

        # We need to mock calculate_adx/rsi/sma inside the module if they are complex,
        # or rely on the module's implementation using pandas.
        # The module uses trading_utils implementations.

        signal, confidence, metadata = mcx_natural_gas_trend.generate_signal(df)

        # Note: With pure linear data, RSI might be 100. ADX might be high.
        # SMA20 > SMA50 is guaranteed after period 50.

        self.assertEqual(signal, "BUY", f"Expected BUY but got {signal}. Metadata: {metadata}")
        self.assertEqual(metadata.get("reason"), "trend_confirmed")

    def test_sell_signal(self):
        # Downtrend/Exit: SMA20 < SMA50 OR RSI < 45

        df = self.base_df.copy()

        # Linear downtrend
        prices = np.linspace(200, 100, 100)
        df['close'] = prices
        df['high'] = prices + 2
        df['low'] = prices - 2

        signal, confidence, metadata = mcx_natural_gas_trend.generate_signal(df)

        self.assertEqual(signal, "SELL", f"Expected SELL but got {signal}. Metadata: {metadata}")
        self.assertEqual(metadata.get("reason"), "trend_reversal")

    def test_insufficient_data(self):
        df = self.base_df.iloc[:10] # Only 10 rows
        signal, confidence, metadata = mcx_natural_gas_trend.generate_signal(df)
        self.assertEqual(signal, "HOLD")

if __name__ == '__main__':
    unittest.main()
