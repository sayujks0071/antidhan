import vectorbt as vbt
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

def main():
    # Set up symbols and parameters
    symbol = "AAPL"

    # Download data
    print(f"Downloading data for {symbol}...")

    # In vectorbt 0.28+, we can pass period as an argument, and ticker_kwargs is for
    # yfinance Ticker initialization (like proxy, session, etc.)
    # yf.Ticker in newer versions accepts 'session' parameter
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
    total_returns = pf.total_return()

    # Rank the performance based on Total Return
    # Premium (>50%), Moderate (10-50%), and Low (<10%)
    print("\n--- Strategy Performance Ranking ---")

    # In single symbol and parameterless backtest, metrics like total_return()
    # natively return a scalar float in VectorBT 0.28+
    # Handle the difference
    print(f"Type of total_returns: {type(total_returns)}")

    if isinstance(total_returns, (float, np.floating)):
        val = total_returns
    else:
        # Fallback for pandas Series/DataFrame
        val = total_returns.iloc[0]

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
