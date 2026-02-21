import sys
import os
import pandas as pd
import numpy as np

# Adjust path to find the strategy
repo_root = os.getcwd()
sys.path.insert(0, repo_root)
sys.path.insert(0, os.path.join(repo_root, 'openalgo')) # so "import utils" works if utils is in openalgo/

strategies_dir = os.path.abspath(os.path.join(repo_root, 'openalgo/strategies/scripts'))
sys.path.insert(0, strategies_dir)

utils_dir = os.path.abspath(os.path.join(repo_root, 'openalgo/strategies/utils'))
sys.path.insert(0, utils_dir)

try:
    from nse_ema_crossover_rsi import generate_signal, NSEEmaCrossoverRsiStrategy
    # Also import indicators for verification
    from trading_utils import calculate_ema, calculate_rsi
except ImportError as e:
    print(f"Failed to import strategy or utils: {e}")
    # Try to mock if imports fail (which they shouldn't if paths are right)
    sys.exit(1)

def test_nse_ema_crossover():
    print("Testing NSEEmaCrossoverRsiStrategy logic...")

    # Create dummy data - Uptrend scenario (Fast EMA > Slow EMA, RSI High)
    dates = pd.date_range(start='2024-01-01', periods=100, freq='5min')

    # Construct a price series
    # 50 periods flat, 50 periods rising
    close_prices = np.concatenate([np.linspace(100, 100, 50), np.linspace(100, 150, 50)])

    df = pd.DataFrame({
        'open': close_prices,
        'high': close_prices,
        'low': close_prices,
        'close': close_prices,
        'volume': np.random.randint(1000, 10000, 100)
    }, index=dates)

    # 1. Test generate_signal
    try:
        signal, qty, meta = generate_signal(df)
        print(f"Signal: {signal}, Qty: {qty}, Meta: {meta}")

        # Verify indicators manually
        ema_fast = calculate_ema(df['close'], 9).iloc[-1]
        ema_slow = calculate_ema(df['close'], 21).iloc[-1]
        rsi = calculate_rsi(df['close'], 14).iloc[-1]

        print(f"Calculated Indicators: EMA9={ema_fast}, EMA21={ema_slow}, RSI={rsi}")

        if ema_fast > ema_slow and rsi > 50:
            assert signal == 'BUY', f"Expected BUY, got {signal}"

    except Exception as e:
        print(f"generate_signal failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 2. Test SELL scenario
    close_prices_down = np.concatenate([np.linspace(150, 150, 50), np.linspace(150, 100, 50)])
    df_down = pd.DataFrame({
        'open': close_prices_down,
        'high': close_prices_down,
        'low': close_prices_down,
        'close': close_prices_down,
        'volume': np.random.randint(1000, 10000, 100)
    }, index=dates)

    signal_down, _, _ = generate_signal(df_down)
    print(f"Down Trend Signal: {signal_down}")

    ema_fast_down = calculate_ema(df_down['close'], 9).iloc[-1]
    ema_slow_down = calculate_ema(df_down['close'], 21).iloc[-1]
    rsi_down = calculate_rsi(df_down['close'], 14).iloc[-1]
    print(f"Calculated Down Indicators: EMA9={ema_fast_down}, EMA21={ema_slow_down}, RSI={rsi_down}")

    if ema_fast_down < ema_slow_down or rsi_down < 40:
        assert signal_down == 'SELL', f"Expected SELL, got {signal_down}"

    print("Test passed!")

if __name__ == "__main__":
    test_nse_ema_crossover()
