import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath('openalgo/strategies/scripts'))

from my_nse_strategy import generate_signal

def test_strategy():
    # Generate some dummy data that would trigger a BUY
    # Condition: close < lower_band and rsi < 30
    dates = pd.date_range('2023-01-01', periods=50)
    data = {'close': np.linspace(100, 50, 50)} # Downward trend to trigger RSI < 30 and Close < Lower Band
    df = pd.DataFrame(data, index=dates)

    signal, qty, metadata = generate_signal(df)
    print(f"Signal generated: {signal}")
    print(f"Metadata: {metadata}")

if __name__ == '__main__':
    test_strategy()
