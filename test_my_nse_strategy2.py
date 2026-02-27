import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath('openalgo/strategies/scripts'))
from my_nse_strategy import generate_signal

# Let's generate a strong drop to definitely trigger RSI < 30 and Close < Lower Band
df = pd.DataFrame({'close': [100]*20 + [90, 80, 70, 60, 50, 40, 30, 20]})
signal, qty, metadata = generate_signal(df)
print(f"Buy Signal generated: {signal}")
print(f"Metadata: {metadata}")

# Let's generate a strong rise to trigger RSI > 70 and Close > Upper Band
df2 = pd.DataFrame({'close': [100]*20 + [110, 120, 130, 140, 150, 160, 170, 180]})
signal2, qty2, metadata2 = generate_signal(df2)
print(f"Sell Signal generated: {signal2}")
print(f"Metadata: {metadata2}")
