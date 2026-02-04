
import time

import numpy as np
import pandas as pd

from packages.core.indicators import IndicatorCalculator


def bench_breakdown():
    # Create 200 bars data
    n = 200
    df = pd.DataFrame({
        'open': np.random.rand(n) * 100,
        'high': np.random.rand(n) * 100,
        'low': np.random.rand(n) * 100,
        'close': np.random.rand(n) * 100,
        'volume': np.random.randint(100, 1000, n)
    })

    calc = IndicatorCalculator()

    iterations = 1000

    # VWAP
    start = time.time()
    for _ in range(iterations):
        calc._vwap(df)
    print(f"VWAP: {(time.time()-start)/iterations*1000:.3f} ms")

    # ATR
    start = time.time()
    for _ in range(iterations):
        calc._atr(df)
    print(f"ATR: {(time.time()-start)/iterations*1000:.3f} ms")

    # RSI
    start = time.time()
    for _ in range(iterations):
        calc._rsi(df)
    print(f"RSI: {(time.time()-start)/iterations*1000:.3f} ms")

    # ADX
    start = time.time()
    for _ in range(iterations):
        calc._adx(df)
    print(f"ADX: {(time.time()-start)/iterations*1000:.3f} ms")

    # Supertrend
    start = time.time()
    for _ in range(iterations):
        calc._supertrend(df)
    print(f"Supertrend: {(time.time()-start)/iterations*1000:.3f} ms")

    # Bollinger
    start = time.time()
    for _ in range(iterations):
        calc._bollinger_bands(df['close'])
    print(f"Bollinger: {(time.time()-start)/iterations*1000:.3f} ms")

if __name__ == "__main__":
    bench_breakdown()
