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

def test_nse_rsi_macd():
    print("Testing NSE RSI MACD Strategy...")
    try:
        from openalgo.strategies.scripts.nse_rsi_macd_strategy import NSERsiMacdStrategy
        df = pd.DataFrame({
            'close': np.linspace(100, 200, 100),
            'high': np.linspace(105, 205, 100),
            'low': np.linspace(95, 195, 100),
            'open': np.linspace(100, 200, 100),
            'volume': np.random.rand(100) * 1000
        })
        # Use backtest_signal classmethod wrapper
        signal = NSERsiMacdStrategy.backtest_signal(df)
        print(f"NSE RSI MACD Signal: {signal}")
    except Exception as e:
        print(f"NSE RSI MACD Failed: {e}")
        import traceback
        traceback.print_exc()

def test_mcx_crudeoil():
    print("Testing MCX Crude Oil Strategy...")
    try:
        from openalgo.strategies.scripts.mcx_crudeoil_trend_strategy import generate_signal
        df = pd.DataFrame({
            'close': np.linspace(100, 200, 100),
            'high': np.linspace(105, 205, 100),
            'low': np.linspace(95, 195, 100),
            'open': np.linspace(100, 200, 100),
            'volume': np.random.rand(100) * 1000
        })
        signal = generate_signal(df)
        print(f"MCX Crude Oil Signal: {signal}")
    except Exception as e:
        print(f"MCX Crude Oil Failed: {e}")
        import traceback
        traceback.print_exc()

def test_gap_fade():
    print("Testing Gap Fade Strategy...")
    try:
        from openalgo.strategies.scripts.gap_fade_strategy import GapFadeStrategy
        df = pd.DataFrame({
            'timestamp': pd.date_range(start='2026-01-01', periods=100, freq='5min'),
            'open': [100.0]*100,
            'high': [105.0]*100,
            'low': [95.0]*100,
            'close': [100.0]*100,
            'volume': [1000]*100
        })
        df.set_index('timestamp', inplace=True)

        # Manually set last candles to trigger signal
        # Period 98: Prev Candle
        df.iloc[98, df.columns.get_loc('high')] = 105.0
        df.iloc[98, df.columns.get_loc('low')] = 95.0
        df.iloc[98, df.columns.get_loc('close')] = 100.0

        # Period 99: Current Candle (Gap Up, Bearish)
        df.iloc[99, df.columns.get_loc('open')] = 106.0 # Gap Up (> Prev High 105)
        df.iloc[99, df.columns.get_loc('close')] = 104.0 # Bearish (< Open)

        signal = GapFadeStrategy.backtest_signal(df)
        print(f"Gap Fade Signal: {signal}")
    except Exception as e:
        print(f"Gap Fade Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_mcx()
    test_ml_v2()
    test_nse_rsi_macd()
    test_mcx_crudeoil()
    test_gap_fade()
