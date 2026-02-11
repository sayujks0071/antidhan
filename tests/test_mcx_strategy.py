import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime

# Add path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'openalgo')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'openalgo', 'strategies', 'scripts')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'openalgo', 'strategies', 'utils')))

# Mock modules if needed
sys.modules['utils'] = MagicMock()
sys.modules['utils.httpx_client'] = MagicMock()

from openalgo.strategies.scripts.mcx_silver_momentum import MCXStrategy

class TestMCXStrategy(unittest.TestCase):
    def test_check_signals_adaptive_sizing(self):
        # Mock API Client
        mock_client = MagicMock()
        # Mock History
        mock_client.history.return_value = pd.DataFrame({
            'close': [100]*20,
            'high': [102]*20,
            'low': [98]*20,
            'volume': [1000]*20
        })

        params = {
            "period_rsi": 14,
            "period_atr": 14
        }

        # Instantiate
        strat = MCXStrategy("SILVERMXX", "key", "http://host", params)
        strat.client = mock_client
        strat.pm = MagicMock()
        strat.pm.has_position.return_value = False
        strat.pm.calculate_adaptive_quantity_monthly_atr.return_value = 5 # Return int

        # Mock get_monthly_atr return
        strat.get_monthly_atr = MagicMock(return_value=10.0)

        # Mock Data
        strat.data = pd.DataFrame({
            'close': [100.0]*60,
            'high': [105.0]*60,
            'low': [95.0]*60,
            'volume': [1000]*60
        })
        strat.calculate_indicators() # This should use calculate_atr imported

        # Check Signals
        try:
            strat.check_signals()
        except Exception as e:
            self.fail(f"check_signals raised exception: {e}")

        # Verify adaptive sizing was called
        strat.pm.calculate_adaptive_quantity_monthly_atr.assert_called()

if __name__ == '__main__':
    unittest.main()
