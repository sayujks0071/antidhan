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
        missing_index="drop",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    print("Running Dual SMA Crossover Backtest for single symbol...")
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

    # For a parameterless strategy on a single symbol in VectorBT 0.28+,
    # metrics like total_return() natively return a scalar float (numpy.float64)
    if isinstance(total_returns, (float, np.floating)):
        val = float(total_returns)
    else:
        # Fallback if somehow it's a series or something else
        try:
            val = float(total_returns.iloc[0])
        except AttributeError:
            val = float(total_returns)

    ret_pct = val * 100

    # Determine rank based on Total Return: Premium (>50%), Moderate (>=10%), and Low (<10%)
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
