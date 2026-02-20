import unittest
from unittest.mock import MagicMock
import pandas as pd
import numpy as np
import sys
import os

# Add openalgo directory to path
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))

from strategies.utils.trading_utils import PositionManager, calculate_atr

class TestPositionManagerATR(unittest.TestCase):
    def setUp(self):
        self.pm = PositionManager("TEST_SYMBOL")

    def test_calculate_adaptive_quantity_with_client(self):
        # Mock Client
        client = MagicMock()

        # Mock History Data for Monthly ATR (60 days)
        dates = pd.date_range(end=pd.Timestamp.now(), periods=60, freq='D')
        # Create data with High ATR
        # High-Low = 100
        df = pd.DataFrame(index=dates)
        df['high'] = np.linspace(1000, 1100, 60) + 50
        df['low'] = np.linspace(1000, 1100, 60) - 50
        df['close'] = np.linspace(1000, 1100, 60)
        df['open'] = df['close']
        df['volume'] = 1000

        # Ensure timestamp column exists as APIClient.history usually returns it
        df['timestamp'] = df.index.view('int64') // 10**9

        client.history.return_value = df

        # Call calculate_adaptive_quantity with client
        # Intraday ATR is small (e.g., 10), Monthly ATR is approx 100

        capital = 100000
        risk_pct = 1.0 # Risk 1000
        price = 1000
        intraday_atr = 10.0

        qty = self.pm.calculate_adaptive_quantity(capital, risk_pct, intraday_atr, price, client=client)

        # Expected Monthly ATR ~ 100
        # Stop Loss Dist = 2 * 100 = 200
        # Risk Amount = 1000
        # Qty = 1000 / 200 = 5

        # If it used Intraday ATR (10):
        # Stop Loss = 20
        # Qty = 1000 / 20 = 50

        # We expect 5
        self.assertLess(qty, 10, "Should use Monthly ATR which is higher (lower qty)")
        self.assertEqual(qty, 5)

        # Verify client.history was called
        client.history.assert_called_once()

    def test_calculate_adaptive_quantity_without_client(self):
        capital = 100000
        risk_pct = 1.0 # Risk 1000
        price = 1000
        intraday_atr = 10.0

        qty = self.pm.calculate_adaptive_quantity(capital, risk_pct, intraday_atr, price)

        # Should use Intraday ATR
        # Stop Loss = 20
        # Qty = 1000 / 20 = 50

        self.assertEqual(qty, 50)

if __name__ == '__main__':
    unittest.main()
