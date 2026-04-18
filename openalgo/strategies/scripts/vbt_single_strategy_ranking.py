import vectorbt as vbt
import numpy as np
import pandas as pd

def main():
    # Set up symbol
    symbol = "BTC-USD"
    print(f"Downloading data for {symbol}...")

    # In vectorbt 0.28+, we can pass period as an argument, and ticker_kwargs is for
    # yfinance Ticker initialization (like proxy, session, etc.)
    # Single symbol download
    data = vbt.YFData.download(
        symbol,
        period="1y",
        missing_index="drop",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    print("Running Dual SMA Crossover Backtest on single symbol...")
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
    # For single symbol, total_return() might be a scalar float instead of a Series
    total_returns = pf.total_return()

    print("\n--- Strategy Performance Ranking ---")

    if isinstance(total_returns, (float, int, np.floating, np.integer)):
        ret_pct = float(total_returns) * 100
    elif isinstance(total_returns, pd.Series):
        if symbol in total_returns.index:
            ret_pct = total_returns[symbol] * 100
        else:
            # Fallback
            ret_pct = total_returns.iloc[0] * 100
    else:
        # Unexpected type
        print(f"Unexpected type for total_returns: {type(total_returns)}")
        ret_pct = 0.0

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
