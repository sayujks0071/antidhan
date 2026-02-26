
import sys
import os
import pandas as pd
import numpy as np

# Set path so strategy can find its imports
sys.path.insert(0, os.path.abspath("openalgo/strategies/scripts"))

# Mock classes for testing logic
class MockClient:
    def __init__(self, api_key="TEST", host="http://localhost"):
        self.api_key = api_key
        self.host = host

# Properly Mock trading_utils functions to match signatures
def mock_calculate_rsi(series, period=14):
    return pd.Series(60, index=series.index) # Always > 55

def mock_calculate_ema(series, period=50):
    return series.rolling(period).mean() - 5 # Always below price for uptrend

def mock_calculate_adx(df, period=14):
    return pd.Series(30, index=df.index) # Always > 25

def mock_is_market_open(exchange="MCX"):
    return True

# Mock PositionManager
class MockPM:
    def __init__(self, symbol):
        self.position = 0
        self.entry_price = 0
    def has_position(self):
        return False
    def update_position(self, qty, price, side):
        pass
    def load_state(self):
        pass

# Inject mocks
import types
mock_utils = types.ModuleType("trading_utils")
mock_utils.APIClient = MockClient
mock_utils.PositionManager = MockPM
mock_utils.is_market_open = mock_is_market_open
mock_utils.calculate_rsi = mock_calculate_rsi
mock_utils.calculate_ema = mock_calculate_ema
mock_utils.calculate_adx = mock_calculate_adx

sys.modules["trading_utils"] = mock_utils
# Also map under different paths just in case
sys.modules["utils.trading_utils"] = mock_utils
sys.modules["openalgo.strategies.utils.trading_utils"] = mock_utils

def test_zinc_trend():
    try:
        from mcx_zinc_trend_strategy import generate_signal, MCXStrategy
    except ImportError as e:
        print(f"Failed to import strategy: {e}")
        return

    # Create synthetic data
    print("Generating synthetic data...")
    dates = pd.date_range(start="2024-01-01", periods=100, freq="15min")
    df = pd.DataFrame(index=dates)
    # Price rising from 200 to 300
    df['close'] = np.linspace(200, 300, 100)
    df['high'] = df['close'] + 2
    df['low'] = df['close'] - 2
    df['open'] = df['close']
    df['volume'] = 1000

    print("Testing generate_signal (Expecting BUY)...")
    # With our mocks:
    # Price > EMA (Price - 5) -> True
    # RSI = 60 > 55 -> True
    # ADX = 30 > 25 -> True

    signal, conf, meta = generate_signal(df, client=MockClient())
    print(f"Result: {signal}, {conf}, {meta}")

    if signal == "BUY":
        print("SUCCESS: Buy signal generated correctly.")
    else:
        print(f"FAILURE: Expected BUY, got {signal}.")

if __name__ == "__main__":
    test_zinc_trend()
