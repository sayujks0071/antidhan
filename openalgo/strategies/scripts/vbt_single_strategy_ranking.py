import vectorbt as vbt
import numpy as np
import pandas as pd

def main():
    # Set up a single symbol
    symbol = "BTC-USD"

    print(f"Downloading data for {symbol}...")

    # YFData.download: period passed directly, ticker_kwargs valid params
    data = vbt.YFData.download(
        symbol,
        period="1y",
        missing_index="drop",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    print("Running Dual SMA Crossover Backtest...")

    # Calculate MAs
    fast_ma = vbt.MA.run(price, 10)
    slow_ma = vbt.MA.run(price, 50)

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
    # In VectorBT 0.28+ with single symbol, total_return() natively returns a scalar float
    total_ret = pf.total_return()

    if isinstance(total_ret, (pd.Series, pd.DataFrame)):
        ret_val = float(total_ret.iloc[0])
    else:
        ret_val = float(total_ret)

    ret_pct = ret_val * 100

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
