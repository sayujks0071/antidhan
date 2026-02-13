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
    df = pd.DataFrame({
        'open': np.random.rand(100) * 100,
        'high': np.random.rand(100) * 100,
        'low': np.random.rand(100) * 100,
        'close': np.linspace(100, 150, 100), # Uptrend
        'volume': np.random.randint(1000, 10000, 100)
    }, index=dates)

    # Run generate_signal
    try:
        signal, qty, meta = generate_signal(df)
        print(f"Signal: {signal}, Qty: {qty}, Meta: {meta}")
    except Exception as e:
        print(f"generate_signal failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Verify indicator calculation
    strat = NSERsiMacdStrategy(symbol="TEST", api_key="dummy", port=5001)
    df_calc = df.copy()
    try:
        strat.calculate_signal(df_calc)
        if 'rsi' in df_calc.columns and 'macd' in df_calc.columns and 'signal' in df_calc.columns:
            print("Indicators calculated successfully: RSI, MACD, Signal found.")
        else:
            print(f"Indicators missing. Columns: {df_calc.columns}")
            sys.exit(1)
    except Exception as e:
        print(f"calculate_signal failed: {e}")
        sys.exit(1)

    print("Test passed!")

if __name__ == "__main__":
    test_nse_rsi_macd()
