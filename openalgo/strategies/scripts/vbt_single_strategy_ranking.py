import os
import sys

# Ensure proper path for local imports if needed
script_dir = os.path.dirname(os.path.abspath(__file__))
strategies_dir = os.path.dirname(script_dir)
root_dir = os.path.dirname(strategies_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
if strategies_dir not in sys.path:
    sys.path.insert(0, strategies_dir)

import vectorbt as vbt
import pandas as pd
import numpy as np
import pandas_ta_classic as ta

def run_backtest():
    """
    Run a VectorBT backtest on a single symbol/strategy.
    Ranks the total return as Premium (>50%), Moderate (>=10%), or Low (<10%).
    Handles scalar return values natively for parameterless indicators.
    """
    symbol = "BTC-USD"
    # Use ticker_kwargs={} for compatibility with vbt 0.28+ YFData
    data = vbt.YFData.download(symbol, period="1y", ticker_kwargs={})
    price = data.get("Close")

    # Simple Moving Average Crossover strategy
    fast_ma = vbt.MA.run(price, 10)
    slow_ma = vbt.MA.run(price, 50)
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Portfolio simulation
    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=100)
    total_return = pf.total_return()

    # In vectorbt 0.28, parameterless indicators on a single symbol often return a scalar.
    # If it is a Pandas Series, we extract the scalar value.
    if isinstance(total_return, pd.Series):
        total_return_val = total_return.iloc[0]
    else:
        total_return_val = total_return

    rank = "Low"
    if total_return_val > 0.5:
        rank = "Premium"
    elif total_return_val >= 0.1:
        rank = "Moderate"

    print(f"Total Return: {total_return_val:.2%}")
    print(f"Strategy Rank: {rank}")

if __name__ == "__main__":
    run_backtest()
