import sys
import os
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

# Adjust path to import from scripts
# Assuming this test is in openalgo/strategies/tests/
# We need to add openalgo/strategies/scripts/ to path
current_dir = os.path.dirname(os.path.abspath(__file__))
scripts_dir = os.path.abspath(os.path.join(current_dir, '../scripts'))
if scripts_dir not in sys.path:
    sys.path.append(scripts_dir)

# We also need to ensure openalgo/strategies/utils is in path because strategy_template imports from there
# Although strategy_template does this itself, doing it here helps avoid import errors before the module loads
utils_dir = os.path.abspath(os.path.join(current_dir, '../utils'))
if utils_dir not in sys.path:
    sys.path.append(utils_dir)

# Import the module to be tested
# We wrap this in try-except or just import, assuming path is correct
try:
    from strategy_template import YourStrategy, generate_signal, ATR_SL_MULTIPLIER, ATR_TP_MULTIPLIER
except ImportError:
    # Fallback if running from root
    sys.path.append('openalgo/strategies/scripts')
    from strategy_template import YourStrategy, generate_signal, ATR_SL_MULTIPLIER, ATR_TP_MULTIPLIER

class TestStrategyTemplate:
    def setup_method(self):
        # Create a dummy DataFrame with enough data for indicators (ATR=14, VolAvg=20)
        dates = pd.date_range(start='2024-01-01', periods=100, freq='5min')
        self.df = pd.DataFrame({
            'datetime': dates,
            'open': [100.0] * 100,
            'high': [105.0] * 100,
            'low': [95.0] * 100,
            'close': [102.0] * 100,
            'volume': [1000] * 100
        })
        # Add some variation to allow ATR calculation
        for i in range(100):
            self.df.loc[i, 'high'] = 105.0 + (i % 5)
            self.df.loc[i, 'low'] = 95.0 - (i % 5)
            self.df.loc[i, 'close'] = 100.0 + (i % 3)

    def test_initialization(self):
        # Mock APIClient to avoid connection attempts
        with patch('strategy_template.APIClient') as MockClient:
            with patch('strategy_template.PositionManager') as MockPM:
                # We also need to mock os.getenv to avoid missing API key warning/error
                with patch.dict(os.environ, {'OPENALGO_API_KEY': 'dummy'}):
                    strategy = YourStrategy(symbol='TEST', api_key='dummy')
                    assert strategy.symbol == 'TEST'
                    assert strategy.quantity == 10
                    assert strategy.name == 'StrategyName_TEST'

    def test_generate_signal_structure(self):
        action, score, details = generate_signal(self.df)

        assert action in ['BUY', 'SELL', 'HOLD']
        assert isinstance(score, float)
        assert isinstance(details, dict)

        required_keys = ['atr', 'quantity', 'sl', 'tp']
        for key in required_keys:
            assert key in details, f"Missing key: {key}"

    def test_risk_parameters_usage(self):
        action, score, details = generate_signal(self.df)

        atr = details.get('atr', 0)
        price = details.get('close', 0)
        sl = details.get('sl', 0)
        tp = details.get('tp', 0)

        if atr > 0:
            # Verify SL/TP logic matches constants
            sl_dist = price - sl
            tp_dist = tp - price

            # Allow small floating point differences
            assert abs(sl_dist - (ATR_SL_MULTIPLIER * atr)) < 0.01, f"SL Dist: {sl_dist}, Exp: {ATR_SL_MULTIPLIER * atr}"
            assert abs(tp_dist - (ATR_TP_MULTIPLIER * atr)) < 0.01, f"TP Dist: {tp_dist}, Exp: {ATR_TP_MULTIPLIER * atr}"

    def test_empty_dataframe(self):
        empty_df = pd.DataFrame()
        action, score, details = generate_signal(empty_df)
        assert action == 'HOLD'
        assert score == 0.0
        assert details == {}

    def test_small_dataframe(self):
        # DataFrame smaller than required (50 rows in template)
        small_df = self.df.head(10)
        action, score, details = generate_signal(small_df)
        assert action == 'HOLD'
        assert score == 0.0
        assert details == {}
