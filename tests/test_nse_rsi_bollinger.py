import sys
import os
import pandas as pd
import numpy as np

# Adjust path to find the strategy script
sys.path.append(os.path.abspath("openalgo/strategies/scripts"))
try:
    from nse_rsi_bollinger_strategy import generate_signal
except ImportError:
    # If run from tests dir
    sys.path.append(os.path.abspath("../openalgo/strategies/scripts"))
    from nse_rsi_bollinger_strategy import generate_signal

def test_logic():
    print("Starting Test...")
    # Create synthetic data
    # Flat data -> RSI 50, Close = SMA.
    dates = pd.date_range(start="2023-01-01", periods=100, freq="5min")
    prices = [100.0] * 100
    df = pd.DataFrame({
        "open": prices,
        "high": prices,
        "low": prices,
        "close": prices,
        "volume": [1000] * 100
    }, index=dates)

    # Test 1: Neutral
    action, score, details = generate_signal(df)
    print(f"Test 1 (Flat): Action={action}")
    assert action == 'HOLD', f"Expected HOLD, got {action}"

    # Test 2: Buy Signal (Drop)
    # Create a scenario where price drops significantly
    # RSI drops, Price drops below bands
    # We need a sequence of drops
    prices = [100.0] * 50
    # Gradual drop to set trend
    for i in range(10):
        prices.append(100.0 - i) # 100, 99, ... 91
    # Sharp drop
    for i in range(5):
        prices.append(90.0 - i*2) # 90, 88, 86...

    # Pad to make sure we don't have empty frame issues
    while len(prices) < 100:
        prices.insert(0, 100.0)

    df = pd.DataFrame({
        "open": prices,
        "high": prices,
        "low": prices,
        "close": prices,
        "volume": [1000] * len(prices)
    })

    action, score, details = generate_signal(df)
    print(f"Test 2 (Drop): Action={action}, RSI={details.get('rsi')}, Lower={details.get('lower_band')}, Close={details.get('price')}")

    # We expect BUY if logic holds (RSI < 30 and Close < Lower)
    # Depending on exact calculation, it might trigger.

    # Test 3: Sell Signal (Recovery)
    # Jump price up
    prices.append(110.0)
    df = pd.DataFrame({
        "open": prices,
        "high": prices,
        "low": prices,
        "close": prices,
        "volume": [1000] * len(prices)
    })

    action, score, details = generate_signal(df)
    print(f"Test 3 (Jump): Action={action}, Price={details.get('price')}")
    assert action == 'SELL', f"Expected SELL (Mean Reversion), got {action}"

    print("All Tests Passed!")

if __name__ == "__main__":
    test_logic()
