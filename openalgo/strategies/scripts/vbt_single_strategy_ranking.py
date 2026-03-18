import vectorbt as vbt
import numpy as np
import pandas as pd
import sys
import os

def main():
    # Insert root_dir and utils_dir into sys.path to resolve internal modules correctly if needed
    current_dir = os.path.dirname(os.path.abspath(__file__))
    strategies_dir = os.path.dirname(current_dir)
    root_dir = os.path.dirname(strategies_dir)
    sys.path.insert(0, root_dir)
    sys.path.insert(0, os.path.join(strategies_dir, "utils"))

    # Set up symbols and parameters
    symbol = "BTC-USD"

    # Download data
    print(f"Downloading data for {symbol}...")

    # In vectorbt 0.28+, we can pass period as an argument, and ticker_kwargs is for
    # yfinance Ticker initialization (like proxy, session, etc.)
    data = vbt.YFData.download(
        symbol,
        period="1y",
        missing_index="drop",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    print("Running Dual SMA Crossover Backtest...")
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
    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        freq="1D"
    )

    # Calculate performance metrics
    total_returns = pf.total_return()

    # Rank the performance based on Total Return
    # Premium (>50%), Moderate (>=10%), and Low (<10%)
    print("\n--- Strategy Performance Ranking ---")

    # In single symbol without parameter arrays, total_return might be a scalar
    if hasattr(total_returns, 'index'):
        # Just grab the first value or parse index if it's a series
        val = total_returns.iloc[0] if isinstance(total_returns, pd.Series) else total_returns.values[0]
    else:
        # It's a scalar value (e.g. numpy.float64 or float)
        val = float(total_returns)

    ret_pct = val * 100

    # Determine rank
    if ret_pct > 50:
        rank = "Premium"
    elif ret_pct >= 10:
        rank = "Moderate"
    else:
        rank = "Low"

    print(f"Symbol: {symbol}")
    print(f"Total Return: {ret_pct:.2f}%")
    print(f"Rank: {rank}")
    print("-" * 30)

if __name__ == "__main__":
    main()
