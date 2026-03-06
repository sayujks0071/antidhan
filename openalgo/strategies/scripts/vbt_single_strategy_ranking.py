import vectorbt as vbt
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

def main():
    # Set up symbols and parameters
    symbol = "BTC-USD"

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

    # In vectorbt, instantiating indicators with single parameters (e.g., vbt.MA.run(price, 10))
    # does not create a parameter MultiIndex by default. Furthermore, if tested on a single symbol
    # without parameter arrays, portfolio metrics like pf.total_return() may return a scalar numpy.float64
    # rather than a pandas object with an .index attribute. Code must check hasattr(total_returns, 'index').

    if hasattr(total_returns, 'index'):
        # Just in case it returns a Series
        if isinstance(total_returns.index, pd.MultiIndex):
            try:
                # Get the value where the symbol level matches
                val = total_returns.xs(symbol, level='symbol').iloc[0]
            except Exception:
                # Fallback: maybe the level name isn't 'symbol'
                # Find the row where the last level value is the symbol
                for idx_tuple, value in total_returns.items():
                    if idx_tuple[-1] == symbol:
                        val = value
                        break
        else:
            val = total_returns.iloc[0] if len(total_returns) > 0 else 0
    else:
        # total_returns is a scalar (e.g., numpy.float64)
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
