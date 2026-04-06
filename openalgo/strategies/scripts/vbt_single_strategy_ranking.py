import vectorbt as vbt
import numpy as np
import pandas as pd

def main():
    symbol = "AAPL"

    print(f"Downloading data for {symbol}...")

    # Download data
    data = vbt.YFData.download(
        symbol,
        period="1y",
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

    # Create portfolio
    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        freq="1D"
    )

    # Calculate performance metrics
    total_returns = pf.total_return()

    # Check type and convert to scalar if necessary
    # In VectorBT 0.28+ when backtesting a single symbol and parameterless strategy,
    # total_return() natively returns a scalar float (e.g., numpy.float64) rather than a pandas Series or DataFrame.
    if isinstance(total_returns, pd.Series):
        ret_val = total_returns.iloc[0]
    elif isinstance(total_returns, pd.DataFrame):
        ret_val = total_returns.iloc[0, 0]
    else:
        # Assuming scalar float
        ret_val = total_returns

    ret_pct = float(ret_val) * 100

    # Rank the performance
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
