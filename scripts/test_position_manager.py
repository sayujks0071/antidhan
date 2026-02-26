
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime, timedelta

# Add path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'openalgo'))
sys.path.append(os.path.join(os.getcwd(), 'openalgo', 'strategies', 'utils'))

from trading_utils import PositionManager

class TestPositionManager(unittest.TestCase):
    def test_adaptive_sizing_monthly_atr(self):
        symbol = "TEST_ADAPTIVE"
        pm = PositionManager(symbol)

        # Mock client history response for get_monthly_atr
        mock_client = MagicMock()

        # Create a mock DataFrame with high/low/close for ATR calculation
        # 30 days of data
        dates = pd.date_range(end=datetime.now(), periods=30)
        df = pd.DataFrame({
            'high': [105]*30,
            'low': [95]*30,
            'close': [100]*30
        }, index=dates)

        mock_client.history.return_value = df

        # Calculate ATR: (105-95)=10. 10 is the TR. ATR should be 10.

        monthly_atr = pm.get_monthly_atr(mock_client, "NSE")
        print(f"Monthly ATR: {monthly_atr}")
        self.assertAlmostEqual(monthly_atr, 10.0, places=1)

        # Now test calculate_adaptive_quantity_monthly_atr
        # Capital = 500000, Risk = 1%, Price = 100
        # Risk Amount = 5000
        # SL Dist = 2 * ATR = 20
        # Qty = 5000 / 20 = 250

        qty = pm.calculate_adaptive_quantity_monthly_atr(
            capital=500000,
            risk_per_trade_pct=1.0,
            monthly_atr=monthly_atr,
            price=100
        )
        print(f"Calculated Qty: {qty}")
        self.assertEqual(qty, 250)

if __name__ == '__main__':
    unittest.main()
