import vectorbt as vbt
import numpy as np
import pandas as pd
import yfinance as yf

def main():
    # Set up a single symbol
    symbol = "BTC-USD"

    print(f"Downloading data for {symbol}...")

    # In vectorbt 0.28+, we can pass period as an argument, and ticker_kwargs is for
    # yfinance Ticker initialization (like session)
    data = vbt.YFData.download(
        symbol,
        period="2y",
        missing_index="drop",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    print("Running Dual SMA Crossover Backtest...")
    fast_window = 10
    slow_window = 50

    fast_ma = vbt.MA.run(price, fast_window)
    slow_ma = vbt.MA.run(price, slow_window)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Portfolio from signals
    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        freq="1D"
    )

    # In VectorBT 0.28+, backtesting a single symbol and parameterless strategy
    # makes total_return() natively return a scalar float (e.g., numpy.float64)
    total_ret = pf.total_return()

    print(f"Total return type: {type(total_ret)}")

    # Convert to percentage
    ret_pct = float(total_ret) * 100

    # Rank
    if ret_pct > 50:
        rank = "Premium"
    elif ret_pct >= 10:
        rank = "Moderate"
    else:
        rank = "Low"

    print("\n--- Single Strategy Performance Ranking ---")
    print(f"Symbol: {symbol}")
    print(f"Total Return: {ret_pct:.2f}%")
    print(f"Rank: {rank}")

if __name__ == "__main__":
    main()
