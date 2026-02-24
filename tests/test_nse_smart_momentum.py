import unittest
import pandas as pd
import numpy as np
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from openalgo.strategies.scripts.nse_smart_momentum import NSESmartMomentumStrategy

class TestNSESmartMomentum(unittest.TestCase):
    def setUp(self):
        # Create dummy data
        dates = pd.date_range(start='2024-01-01', periods=100, freq='5min')
        self.df = pd.DataFrame({
            'open': np.random.rand(100) * 100,
            'high': np.random.rand(100) * 100,
            'low': np.random.rand(100) * 100,
            'close': np.random.rand(100) * 100,
            'volume': np.random.rand(100) * 1000
        }, index=dates)

        # Setup strategy with dummy API key
        self.strategy = NSESmartMomentumStrategy(
            symbol='TEST',
            api_key='dummy',
            port=5000,
            period_rsi=14,
            period_ema=50,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
            rsi_buy=55,
            rsi_sell=45
        )
        # Disable logging for tests
        self.strategy.logger.disabled = True

    def test_calculate_signal_hold(self):
        # Default random data shouldn't trigger a buy easily, or if it does, it's fine.
        # But let's force a HOLD by making price low
        self.df['close'] = 10.0 # Low price
        # And ensure EMA is high (simulated)
        # Actually calculate_signal computes indicators.
        # So if close is constant 10, RSI is 50 (flat), EMA is 10.
        # RSI 50 < 55 (Buy) -> HOLD.

        signal, confidence, meta = self.strategy.calculate_signal(self.df)
        self.assertEqual(signal, 'HOLD')

    def test_calculate_signal_buy(self):
        # Construct a scenario for BUY
        # Close > EMA(50) -> Trend Up
        # RSI > 55
        # MACD > Signal

        # Create a rising trend
        prices = np.linspace(100, 200, 100)
        self.df['close'] = prices

        # With linear rise:
        # EMA(50) will be below Close (lagging) -> OK
        # RSI will be high (100 for pure linear rise usually, or very high) -> OK (>55)
        # MACD: Fast EMA > Slow EMA -> MACD > 0. Signal is lagging MACD -> MACD > Signal -> OK.

        signal, confidence, meta = self.strategy.calculate_signal(self.df)
        self.assertEqual(signal, 'BUY')
        self.assertEqual(confidence, 1.0)
        self.assertIn('rsi', meta)

if __name__ == '__main__':
    unittest.main()
