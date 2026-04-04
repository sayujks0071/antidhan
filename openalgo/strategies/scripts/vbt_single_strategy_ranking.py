import vectorbt as vbt
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

def main():
    # Set up symbols and parameters
    # In VectorBT 0.28+, when backtesting a single symbol and parameterless strategy,
    # metrics like total_return() natively return a scalar float rather than a pandas Series.
    symbol = "BTC-USD"

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
    # Need to specify freq="1D" to prevent UserWarnings during metrics generation
    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        freq="1D"
    )

    # Calculate performance metrics
    total_return_val = pf.total_return()

    # In vectorbt 0.28+ with single symbol, total_return() is a numpy.float64
    # Rank the performance based on Total Return
    # Premium (>50%), Moderate (10-50%), and Low (<10%)
    print("\n--- Strategy Performance Ranking ---")

    # Handle scalar return correctly
    if isinstance(total_return_val, (float, np.float64, int)):
        val = float(total_return_val)
    elif isinstance(total_return_val, pd.Series):
        # Fallback if it somehow returns a series
        val = float(total_return_val.iloc[0])
    else:
        val = float(total_return_val)

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
