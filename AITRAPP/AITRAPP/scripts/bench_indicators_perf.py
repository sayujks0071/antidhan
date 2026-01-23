import time
import pandas as pd
import numpy as np
from packages.core.indicators import IndicatorCalculator

def bench():
    # Create 500 bars data (realistic window)
    n = 500
    df = pd.DataFrame({
        'open': np.random.rand(n) * 100,
        'high': np.random.rand(n) * 100,
        'low': np.random.rand(n) * 100,
        'close': np.random.rand(n) * 100,
        'volume': np.random.randint(100, 1000, n)
    })

    calc = IndicatorCalculator()
    iterations = 2000

    results = {}

    for name, func in [
        ('ATR', lambda: calc._atr(df)),
        ('RSI', lambda: calc._rsi(df)),
        ('ADX', lambda: calc._adx(df)),
        ('Bollinger', lambda: calc._bollinger_bands(df['close'])),
    ]:
        start = time.time()
        for _ in range(iterations):
            func()
        duration = (time.time() - start) / iterations * 1000
        results[name] = duration
        print(f"{name}: {duration:.3f} ms")

if __name__ == "__main__":
    bench()
