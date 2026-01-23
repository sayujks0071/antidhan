
import time
import pandas as pd
import numpy as np
from packages.strategy_foundry.adapters.core_indicators import VectorIndicatorCalculator

def run_benchmark():
    # Setup Data
    N = 100000 # 100k candles
    np.random.seed(42)

    # Generate random OHLC
    close = np.cumsum(np.random.randn(N)) + 10000
    high = close + np.random.rand(N) * 10
    low = close - np.random.rand(N) * 10
    open_ = (high + low) / 2 # Approx

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": np.random.randint(100, 10000, N)
    })

    calc = VectorIndicatorCalculator()

    # Set params
    calc.supertrend_period = 10
    calc.supertrend_multiplier = 3.0

    print(f"Benchmarking Supertrend calculation with {N} candles...")

    # Warmup
    calc.supertrend_series(df.iloc[:1000])

    start_time = time.time()
    iterations = 5

    for _ in range(iterations):
        st, direction = calc.supertrend_series(df)

    end_time = time.time()
    avg_time = (end_time - start_time) / iterations

    print(f"Average time over {iterations} runs: {avg_time:.4f}s")

    # Verification of output (checksum)
    # Use nansum to ignore initial NaNs
    print(f"Checksum (ST sum): {np.nansum(st):.2f}")
    print(f"Checksum (Dir sum): {direction.sum()}")

if __name__ == "__main__":
    run_benchmark()
