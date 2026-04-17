"""
VectorBT Single Strategy Ranking
Implements a single-symbol backtest using VectorBT 0.28+ and ranks
the strategy as Premium, Moderate, or Low based on total return.

CHANGELOG:
- 2026-04-17: Initial creation of the single-strategy ranking script
"""

import vectorbt as vbt
import numpy as np
import pandas as pd
from curl_cffi import requests

def main():
    symbol = "BTC-USD"
    print(f"Downloading data for {symbol}...")

    # Create curl_cffi impersonated session to avoid fetch issues
    session = requests.Session(impersonate='chrome')

    # In vectorbt 0.28+, pass period directly, use ticker_kwargs for initialization
    data = vbt.YFData.download(
        symbol,
        period="1y",
        missing_index="drop",
        ticker_kwargs=dict(session=session)
    )
    price = data.get("Close")

    print(f"Running Dual SMA Crossover Backtest for {symbol}...")
    # Define SMA windows
    fast_window = 10
    slow_window = 50

    # Calculate MAs
    fast_ma = vbt.MA.run(price, fast_window)
    slow_ma = vbt.MA.run(price, slow_window)

    # Generate crossover signals
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Run portfolio backtest
    # Need to specify freq="1D" to prevent UserWarnings during metrics generation
    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        freq="1D"
    )

    # Calculate performance metrics
    total_returns = pf.total_return()

    # Ensure it's treated as a single float scalar
    if isinstance(total_returns, pd.Series):
        if len(total_returns) > 0:
            val = float(total_returns.iloc[0])
        else:
            val = 0.0
    else:
        val = float(total_returns)

    ret_pct = val * 100

    # Rank the performance based on Total Return
    # Premium (>50%), Moderate (10-50%), and Low (<10%)
    if ret_pct > 50:
        rank = "Premium"
    elif ret_pct >= 10:
        rank = "Moderate"
    else:
        rank = "Low"

    print("\n--- Strategy Performance Ranking ---")
    print(f"Symbol: {symbol}")
    print(f"Total Return: {ret_pct:.2f}%")
    print(f"Rank: {rank}")
    print("-" * 30)

if __name__ == "__main__":
    main()
