import vectorbt as vbt
import numpy as np

def main():
    # Set up single symbol
    symbol = "BTC-USD"
    print(f"Downloading data for {symbol}...")

    # Download data with missing_index="drop" and specific ticker_kwargs for vbt 0.28+
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

    # Calculate total return
    # In VectorBT 0.28+ when backtesting a single symbol and parameterless strategy,
    # total_return() natively returns a scalar float (numpy.float64)
    total_ret = pf.total_return()

    if isinstance(total_ret, np.float64) or isinstance(total_ret, float):
        ret_pct = float(total_ret) * 100
    else:
        # Fallback if somehow it returns a pandas structure
        ret_pct = float(total_ret.iloc[0] if hasattr(total_ret, 'iloc') else total_ret) * 100

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
