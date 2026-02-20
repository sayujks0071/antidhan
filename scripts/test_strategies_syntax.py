import sys
import os
import pandas as pd
import numpy as np

# Add repo root to path
sys.path.insert(0, os.getcwd())
# Ensure openalgo/strategies/utils is in path for base_strategy import
sys.path.insert(0, os.path.join(os.getcwd(), 'openalgo'))
sys.path.insert(0, os.path.join(os.getcwd(), 'openalgo', 'strategies', 'utils'))

def test_mcx():
    print("Testing MCX Strategy...")
    try:
        from openalgo.strategies.scripts.mcx_gold_momentum_strategy import generate_signal
        df = pd.DataFrame({
            'close': np.linspace(100, 200, 100), # Up trend
            'high': np.linspace(105, 205, 100),
            'low': np.linspace(95, 195, 100),
            'open': np.linspace(100, 200, 100),
            'volume': np.random.rand(100) * 1000
        })
        # Need enough data for indicators
        signal = generate_signal(df)
        print(f"MCX Signal: {signal}")
    except Exception as e:
        print(f"MCX Failed: {e}")
        import traceback
        traceback.print_exc()

def test_ml_v2():
    print("Testing ML V2 Strategy...")
    try:
        from openalgo.strategies.scripts.advanced_ml_momentum_strategy_v2 import generate_signal
        df = pd.DataFrame({
            'close': np.linspace(100, 200, 100),
            'high': np.linspace(105, 205, 100),
            'low': np.linspace(95, 195, 100),
            'open': np.linspace(100, 200, 100),
            'volume': np.random.rand(100) * 1000
        })
        signal = generate_signal(df)
        print(f"ML V2 Signal: {signal}")
    except Exception as e:
        print(f"ML V2 Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_mcx()
    test_ml_v2()
