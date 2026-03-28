import vectorbt as vbt
import numpy as np

def main():
    # Set up a single symbol
    symbol = "BTC-USD"

    # Download data
    print(f"Downloading data for {symbol}...")

    # In vectorbt 0.28+, we can pass period as an argument, and ticker_kwargs is for
    # yfinance Ticker initialization (like proxy, session, etc.)
    data = vbt.YFData.download(
        symbol,
        period="1y",
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
    total_return = pf.total_return()

    print("\n--- Strategy Performance Ranking ---")

    # Handle scalar return values natively for parameterless indicators / single symbol
    if isinstance(total_return, (float, int, np.number)):
        val = float(total_return)
    else:
        # Fallback if it's a pandas object
        val = float(total_return.iloc[0])

    ret_pct = val * 100

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
