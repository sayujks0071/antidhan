import os
import sys
import pandas as pd
import numpy as np

# Add openalgo directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../openalgo/strategies/scripts')))

from openalgo.strategies.scripts.mcx_naturalgas_mean_reversion import generate_signal

def test_naturalgas():
    # Create mock data
    dates = pd.date_range(start='2026-01-01', periods=100, freq='D')
    # Generate prices that dip below lower bollinger band
    np.random.seed(42)
    base_price = 200
    prices = base_price + np.random.normal(0, 5, 100).cumsum()
    # Force a sharp dip at the end
    prices[-1] = prices[-2] - 30

    df = pd.DataFrame({
        'open': prices,
        'high': prices + 2,
        'low': prices - 2,
        'close': prices,
        'volume': 1000
    }, index=dates)

    signal, strength, meta = generate_signal(df, symbol="NATURALGAS")
    print(f"Signal: {signal}, Strength: {strength}, Meta: {meta}")

if __name__ == '__main__':
    test_naturalgas()
