import sys
import os
import pandas as pd
import numpy as np
import logging

# Add paths
current_dir = os.getcwd()
sys.path.insert(0, os.path.join(current_dir, "openalgo"))
sys.path.insert(0, os.path.join(current_dir, "openalgo/strategies/utils"))
sys.path.insert(0, os.path.join(current_dir, "openalgo/strategies/scripts"))

# Mock httpx to avoid connection errors during init
from unittest.mock import MagicMock
sys.modules['httpx'] = MagicMock()

try:
    from supertrend_vwap_strategy import SuperTrendVWAPStrategy
except ImportError as e:
    print(f"ImportError: {e}")
    # Try alternate import if needed
    try:
        from strategies.scripts.supertrend_vwap_strategy import SuperTrendVWAPStrategy
    except ImportError as e2:
        print(f"ImportError 2: {e2}")
        sys.exit(1)

def test_strategy_logic():
    print("Verifying SuperTrendVWAPStrategy Logic...")

    # Create synthetic data
    # 200 periods to establish EMA200 and other indicators
    dates = pd.date_range(start="2024-01-01", periods=250, freq="5min")
    df = pd.DataFrame({
        "datetime": dates,
        "open": 100.0,
        "high": 100.5,
        "low": 99.5,
        "close": 100.0,
        "volume": 1000.0
    })
    df.set_index("datetime", inplace=True)

    # Create a slow uptrend to keep EMA rising but close to price
    # Close increases from 100 to 105 over 250 periods
    # This keeps deviation low
    df['close'] = np.linspace(100, 105, 250)
    df['high'] = df['close'] + 0.5
    df['low'] = df['close'] - 0.5
    df['open'] = df['close'] - 0.1

    # Volume spike on last candle
    df.iloc[-1, df.columns.get_loc('volume')] = 5000.0

    # Instantiate strategy
    try:
        strategy = SuperTrendVWAPStrategy(symbol="TEST", quantity=1, api_key="test", host="test")
        strategy.logger.setLevel(logging.CRITICAL)

        # Run generate_signal
        signal, score, details = strategy.generate_signal(df)

        print(f"Signal: {signal}")
        print(f"Details: {details}")

        if signal == 'BUY':
            print("✅ Logic Verified: generated BUY signal as expected.")
        else:
            print(f"❌ Logic Verification Failed: expected BUY, got {signal}")
            sys.exit(1)

    except Exception as e:
        print(f"Exception during test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_strategy_logic()
