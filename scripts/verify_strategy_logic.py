import sys
import os
import pandas as pd
import numpy as np

# Setup path to import strategy
repo_root = os.getcwd()
strategies_dir = os.path.join(repo_root, 'openalgo', 'strategies', 'scripts')
utils_dir = os.path.join(repo_root, 'openalgo', 'strategies', 'utils')

sys.path.append(strategies_dir)
sys.path.append(utils_dir)

# Mock BaseStrategy if needed, but better to use the real one if possible.
# However, BaseStrategy needs many things.
# Let's try to import the module.
# The module tries to import BaseStrategy from base_strategy (which is in utils).
# So adding utils_dir to sys.path should work.

try:
    import supertrend_vwap_strategy
except ImportError as e:
    print(f"Failed to import strategy: {e}")
    sys.exit(1)

def verify_logic():
    print("Verifying SuperTrendVWAPStrategy logic...")

    # Create mock DataFrame
    # Needs: close, volume, high, low, open
    dates = pd.date_range(start='2024-01-01', periods=250, freq='5min')
    df = pd.DataFrame(index=dates)
    df['open'] = 100.0
    df['high'] = 105.0
    df['low'] = 95.0
    df['close'] = 102.0
    df['volume'] = 1000.0

    # Make the last candle trigger BUY
    # Conditions:
    # 1. Above VWAP
    # 2. Volume Spike (Volume > Mean + 1.5*Std)
    # 3. Above POC
    # 4. Not Overextended (Abs(Dev) < Threshold)
    # 5. Sector Bullish (Assumed True in backtest)
    # 6. Strong Trend (ADX > Threshold)
    # 7. Uptrend (Close > EMA200)

    # 1. VWAP: We need to mock calculate_intraday_vwap or ensure it works.
    # The strategy calls self.calculate_intraday_vwap(df).
    # We can mock the methods on the instance.

    # Instantiate
    try:
        # We pass dummy args
        strat = supertrend_vwap_strategy.SuperTrendVWAPStrategy(
            symbol="TEST",
            quantity=1,
            api_key="test",
            host="test"
        )
    except Exception as e:
        print(f"Failed to instantiate strategy: {e}")
        # BaseStrategy __init__ might require valid args or env vars.
        # Let's assume it works or we might need to mock.
        return

    # Mock methods to isolate logic
    strat.calculate_intraday_vwap = lambda df: df.assign(vwap=100.0, vwap_dev=0.01)
    strat.calculate_atr = lambda df: 1.0
    strat.analyze_volume_profile = lambda df: (90.0, 10000) # POC Price, POC Vol
    strat.calculate_ema = lambda series, period: pd.Series([90.0]*len(series), index=series.index) # EMA < Close
    strat.calculate_adx = lambda df, period: 30.0 # ADX > 20

    # Set volume spike
    # rolling mean of 20. last volume needs to be > mean + 1.5*std
    # Let's just mock the rolling calc?
    # The code does:
    # vol_mean = df['volume'].rolling(20).mean().iloc[-1]
    # vol_std = df['volume'].rolling(20).std().iloc[-1]
    # So we need enough data. We have 250 rows.
    # Let's set last volume high.
    df.iloc[-1, df.columns.get_loc('volume')] = 5000.0 # Spike

    # Run generate_signal
    try:
        action, score, details = strat.generate_signal(df)
        print(f"Result: Action={action}, Score={score}")

        if action == 'BUY':
            print("Logic Verification: PASSED")
        else:
            print(f"Logic Verification: FAILED (Expected BUY, got {action})")

    except NameError as e:
        print(f"Logic Verification: FAILED with NameError: {e}")
        print("Bug confirmed: 'last' is undefined in generate_signal.")
    except Exception as e:
        print(f"Logic Verification: FAILED with Exception: {e}")

if __name__ == "__main__":
    verify_logic()
