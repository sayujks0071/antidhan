import vectorbt as vbt
import pandas as pd
import numpy as np

def main():
    symbol = "BTC-USD"
    print(f"Downloading data for {symbol}...")

    # For VectorBT 0.28+:
    # Use ticker_kwargs for YFData (like session=None instead of passing it explicitly if it isn't expected)
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

    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        freq="1D"
    )

    total_return = pf.total_return()

    print("\n--- Strategy Performance Ranking ---")
    print(f"Symbol: {symbol}")

    # Handle scalar float return for single-symbol metric
    if isinstance(total_return, pd.Series):
        ret_val = total_return.iloc[0]
    elif isinstance(total_return, np.ndarray):
        if total_return.size > 0:
            ret_val = total_return.item(0)
        else:
            ret_val = 0.0
    else:
        ret_val = float(total_return)

    ret_pct = ret_val * 100

    if ret_pct > 50:
        rank = "Premium"
    elif ret_pct >= 10:
        rank = "Moderate"
    else:
        rank = "Low"

    print(f"Total Return: {ret_pct:.2f}%")
    print(f"Rank: {rank}")
    print("-" * 30)

if __name__ == "__main__":
    main()
