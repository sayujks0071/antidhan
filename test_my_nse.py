import sys
import pandas as pd
import numpy as np

sys.path.insert(0, 'openalgo/strategies/scripts')
from my_nse_strategy import generate_signal

df = pd.DataFrame({
    'close': [100]*20 + [50], # Last close very low
})

# With low close, rsi will be low and lower band will be breached
signal, qty, meta = generate_signal(df)
print("Signal 1 (expected BUY):", signal)

df = pd.DataFrame({
    'close': [100]*20 + [150], # Last close very high
})
signal, qty, meta = generate_signal(df)
print("Signal 2 (expected HOLD):", signal) # Since entry is just for BUY, it shouldn't return SELL for entry
