import vectorbt as vbt
import numpy as np
import pandas as pd

def main():
    # Set up symbols and parameters
    symbol = "BTC-USD"
    symbols = [symbol]

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
    # In VectorBT 0.28+, when backtesting a single symbol and parameterless strategy,
    # metrics like total_return() natively return a scalar float
    total_return = pf.total_return()

    # Rank the performance based on Total Return
    print("\n--- Strategy Performance Ranking ---")

    # In single symbol backtests, total_return is a scalar float
    # We check if it is a numpy float or python float to be safe
    if isinstance(total_return, (float, np.float64, np.float32)):
        ret_pct = total_return * 100
    else:
        # Fallback if it somehow returned a series (e.g. if we downloaded multiple symbols by mistake)
        if isinstance(total_return.index, pd.MultiIndex):
            val = total_return.xs(symbol, level='symbol').iloc[0]
        else:
            val = total_return[symbol]
        ret_pct = val * 100

    # Premium (>50%), Moderate (>=10%), and Low (<10%)
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
