import vectorbt as vbt
import numpy as np
import pandas as pd

def main():
    # Set up a single symbol
    symbol = "BTC-USD"

    # Download data
    print(f"Downloading data for {symbol}...")

    # In vectorbt 0.28+, pass period as a direct argument.
    # ticker_kwargs is for yfinance Ticker initialization
    data = vbt.YFData.download(
        symbol,
        period="1y",
        missing_index="drop",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    print("Running SMA Crossover Backtest on single symbol...")
    # Define SMA windows
    fast_window = 10
    slow_window = 50

    # Calculate MAs using single parameters
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

    print("\n--- Strategy Performance Ranking ---")

    # Handle scalar numpy.float64 return value
    if hasattr(total_returns, 'index'):
        # Just in case it returns a pandas object
        if hasattr(total_returns.index, 'levels'):  # MultiIndex check
            try:
                val = total_returns.xs(symbol, level='symbol').iloc[0]
            except Exception:
                for idx_tuple, value in total_returns.items():
                    if idx_tuple[-1] == symbol:
                        val = value
                        break
        else:
            val = total_returns[symbol] if symbol in total_returns else float(total_returns.iloc[0])
    else:
        # It's a scalar (e.g., numpy.float64)
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
