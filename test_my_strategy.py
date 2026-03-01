import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), 'openalgo'))
sys.path.insert(0, os.path.join(os.getcwd(), 'openalgo', 'strategies', 'scripts'))

from openalgo.strategies.scripts.mcx_naturalgas_mean_reversion import generate_signal

df = pd.DataFrame({
    'close': np.linspace(100, 50, 100), # Down trend
    'high': np.linspace(105, 55, 100),
    'low': np.linspace(95, 45, 100),
    'open': np.linspace(100, 50, 100),
    'volume': np.random.rand(100) * 1000
})

print(generate_signal(df))
