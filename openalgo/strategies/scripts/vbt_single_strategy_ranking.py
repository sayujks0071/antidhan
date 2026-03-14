import vectorbt as vbt
import numpy as np
import pandas as pd

def main():
    symbol = "BTC-USD"
    print(f"Downloading data for {symbol}...")

    # VectorBT 0.28+ specific arguments
    # period passed directly, ticker_kwargs for yfinance Ticker initialization
    data = vbt.YFData.download(
        symbol,
        period="1y",
        missing_index="drop",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    print("Running Dual SMA Crossover Backtest on single symbol...")
    fast_ma = vbt.MA.run(price, 10)
    slow_ma = vbt.MA.run(price, 50)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # VectorBT 0.28+ freq="1D" to prevent UserWarnings
    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        freq="1D"
    )

    total_returns = pf.total_return()

    # If tested on a single symbol without parameter arrays, total_return() might be a scalar
    if hasattr(total_returns, 'index'):
        # Assuming it's a Series with single value
        ret = float(total_returns.iloc[0])
    else:
        # Scalar
        ret = float(total_returns)

    ret_pct = ret * 100

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
    print("-" * 30)

if __name__ == "__main__":
    main()
