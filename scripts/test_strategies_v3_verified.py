import sys
import os
import pandas as pd
import numpy as np

# Add repo root to path
sys.path.insert(0, os.getcwd())
# Add strategies scripts folder to path so `import strategy_preamble` works inside the strategies
sys.path.insert(0, os.path.join(os.getcwd(), 'openalgo', 'strategies', 'scripts'))

def test_nse_rsi_macd_v2():
    print("Testing NSE RSI MACD Strategy V2...")
    try:
        from openalgo.strategies.scripts.nse_rsi_macd_strategy_v2 import NSERsiMacdStrategyV2
        df = pd.DataFrame({
            'close': np.linspace(100, 200, 100),
            'high': np.linspace(105, 205, 100),
            'low': np.linspace(95, 195, 100),
            'open': np.linspace(100, 200, 100),
            'volume': np.random.rand(100) * 1000
        })
        # Use backtest_signal classmethod wrapper
        signal = NSERsiMacdStrategyV2.backtest_signal(df)
        print(f"NSE RSI MACD V2 Signal: {signal}")
    except Exception as e:
        print(f"NSE RSI MACD V2 Failed: {e}")
        import traceback
        traceback.print_exc()

def test_nse_rsi_macd_v3():
    print("Testing NSE RSI MACD Strategy V3...")
    try:
        from openalgo.strategies.scripts.nse_rsi_macd_strategy_v3 import NSERsiMacdStrategyV3
        df = pd.DataFrame({
            'close': np.linspace(100, 200, 100),
            'high': np.linspace(105, 205, 100),
            'low': np.linspace(95, 195, 100),
            'open': np.linspace(100, 200, 100),
            'volume': np.random.rand(100) * 1000
        })
        # Use backtest_signal classmethod wrapper
        signal = NSERsiMacdStrategyV3.backtest_signal(df)
        print(f"NSE RSI MACD V3 Signal: {signal}")
    except Exception as e:
        print(f"NSE RSI MACD V3 Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_nse_rsi_macd_v2()
    test_nse_rsi_macd_v3()
