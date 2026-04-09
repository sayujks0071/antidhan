import vectorbt as vbt
import numpy as np
import pandas as pd

def main():
    # Use single symbol as specified by the task and memory
    symbol = "BTC-USD"
    print(f"Downloading data for {symbol}...")

    # In vectorbt 0.28+, use correct arguments
    data = vbt.YFData.download(
        symbol,
        period="1y",
        missing_index="drop",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    print("Running Dual SMA Crossover Backtest for single symbol...")
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

    total_ret = pf.total_return()

    print(f"Total return type: {type(total_ret)}")

    # In VectorBT 0.28+, total_return() natively returns a scalar float for a
    # backtesting a single symbol and parameterless strategy
    if isinstance(total_ret, (float, np.floating)):
        ret_pct = float(total_ret) * 100
    else:
        # Fallback just in case
        ret_pct = float(total_ret.iloc[0]) * 100 if hasattr(total_ret, 'iloc') else float(total_ret) * 100

    # Rank strategy based on result
    if ret_pct > 50:
        rank = "Premium"
    elif ret_pct >= 10:
        rank = "Moderate"
    else:
        rank = "Low"

    print(f"\n--- Single Strategy Performance Ranking ---")
    print(f"Symbol: {symbol}")
    print(f"Total Return: {ret_pct:.2f}%")
    print(f"Rank: {rank}")

if __name__ == "__main__":
    main()
