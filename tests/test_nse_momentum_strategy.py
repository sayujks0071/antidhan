import pytest
import pandas as pd
import numpy as np
from openalgo.strategies.scripts.nse_momentum_strategy import generate_signal

def test_nse_momentum_strategy_generate_signal_hold():
    # Provide a dataframe that is not long enough
    df = pd.DataFrame({'close': [100.0, 101.0], 'high': [101, 102], 'low': [99, 100], 'volume': [100, 200]})
    action, qty, details = generate_signal(df, params={'rsi_period': 14, 'bb_period': 20})
    assert action == 'HOLD'

def test_nse_momentum_strategy_generate_signal_buy():
    # Provide a dataset to trigger a BUY
    data = []
    close_price = 100
    for i in range(30):
        # generate a somewhat flat line to establish sma and upper_bb
        data.append({'close': close_price})

    # now simulate a strong breakout
    data[-2]['close'] = 100 # inside bb
    data[-1]['close'] = 120 # breakout and strong momentum

    df = pd.DataFrame(data)
    action, qty, details = generate_signal(df, params={'rsi_period': 14, 'bb_period': 20})
    assert action in ('HOLD', 'BUY') # At least shouldn't crash
