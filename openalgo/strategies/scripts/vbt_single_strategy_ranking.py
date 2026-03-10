import vectorbt as vbt
import numpy as np
import pandas as pd

def main():
    symbol = "BTC-USD"
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
    total_returns = pf.total_return()

    print("\n--- Strategy Performance Ranking ---")

    # Handle scalar return values vs pandas objects
    if hasattr(total_returns, 'index'):
        if isinstance(total_returns.index, pd.MultiIndex):
            try:
                val = total_returns.xs(symbol, level='symbol').iloc[0]
            except Exception:
                for idx_tuple, value in total_returns.items():
                    if idx_tuple[-1] == symbol:
                        val = value
                        break
        else:
            try:
                val = total_returns[symbol]
            except KeyError:
                # If symbol is not in index, just take the first value
                val = total_returns.iloc[0]
    else:
        # It's a scalar value (e.g. numpy.float64)
        val = total_returns

    ret_pct = float(val) * 100

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
