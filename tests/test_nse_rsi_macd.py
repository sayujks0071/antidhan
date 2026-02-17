import sys
import os
import pandas as pd
import numpy as np

# Adjust path to find the strategy
# Current dir is repo root. File is in tests/
# Strategy is in openalgo/strategies/scripts/
strategies_dir = os.path.abspath(os.path.join(os.getcwd(), 'openalgo/strategies/scripts'))
sys.path.insert(0, strategies_dir)

# Also need utils
utils_dir = os.path.abspath(os.path.join(os.getcwd(), 'openalgo/strategies/utils'))
sys.path.insert(0, utils_dir)

# Also project root
sys.path.insert(0, os.getcwd())

try:
    from nse_rsi_macd_strategy import generate_signal, NSERsiMacdStrategy
except ImportError as e:
    print(f"Failed to import strategy: {e}")
    # Try adding the folder to sys.path explicitly
    sys.path.append('openalgo/strategies/scripts')
    try:
        from nse_rsi_macd_strategy import generate_signal, NSERsiMacdStrategy
    except ImportError as e2:
        print(f"Failed to import strategy again: {e2}")
        sys.exit(1)

def test_nse_rsi_macd():
    print("Testing NSERsiMacdStrategy logic...")

    # Create dummy data
    dates = pd.date_range(start='2024-01-01', periods=100, freq='5min')
    # Create uptrend with some volatility
    close = np.linspace(100, 150, 100) + np.random.normal(0, 1, 100)

    df = pd.DataFrame({
        'open': close - 1,
        'high': close + 1,
        'low': close - 1,
        'close': close,
        'volume': np.random.randint(1000, 10000, 100)
    }, index=dates)

    # Run generate_signal (Backtest wrapper)
    try:
        signal, qty, meta = generate_signal(df)
        print(f"Signal: {signal}, Qty: {qty}, Meta: {meta}")
    except Exception as e:
        print(f"generate_signal failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Verify direct method
    strat = NSERsiMacdStrategy(symbol="TEST", api_key="dummy", port=5001)
    df_calc = df.copy()
    try:
        # Use get_signal instead of calculate_signal
        sig, conf, meta = strat.get_signal(df_calc)
        print(f"Direct Signal: {sig}, Conf: {conf}, Meta: {meta}")

        # Verify result format
        if sig in ['BUY', 'SELL', 'HOLD']:
            print("Signal format valid.")
        else:
            print(f"Invalid signal: {sig}")
            sys.exit(1)

    except Exception as e:
        print(f"get_signal failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("Test passed!")

if __name__ == "__main__":
    test_nse_rsi_macd()
