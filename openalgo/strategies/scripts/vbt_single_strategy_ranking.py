import vectorbt as vbt
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

def main():
    # Set up a single symbol and parameters
    symbols = ["AAPL"]

    # Download data
    print(f"Downloading data for {symbols}...")

    # In vectorbt 0.28+, we can pass period as an argument, and ticker_kwargs is for
    # yfinance Ticker initialization (like proxy, session, etc.)
    # yf.Ticker in newer versions accepts 'session' parameter
    data = vbt.YFData.download(
        symbols,
        period="1y",
        missing_index="drop",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    print("Running Dual SMA Crossover Backtest on a single strategy...")
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

    # We only have one symbol, let's extract it
    # total_returns could be a scalar (float) if only 1 symbol is tested and no multi-params
    if hasattr(total_returns, "index") and isinstance(total_returns.index, pd.MultiIndex):
        try:
            val = total_returns.xs(symbols[0], level='symbol').iloc[0]
        except Exception:
            # Fallback
            for idx_tuple, value in total_returns.items():
                if idx_tuple[-1] == symbols[0]:
                    val = value
                    break
    else:
        # Check if it's a pandas Series
        if isinstance(total_returns, pd.Series):
            val = total_returns[symbols[0]]
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
    print(f"Symbol: {symbols[0]}")
    print(f"Total Return: {ret_pct:.2f}%")
    print(f"Rank: {rank}")
    print("-" * 30)

if __name__ == "__main__":
    main()
