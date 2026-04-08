import vectorbt as vbt
import numpy as np

def main():
    symbol = "BTC-USD"
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
    # In vectorbt 0.28+, when backtesting a single symbol and parameterless strategy,
    # total_return() natively returns a scalar float.
    total_return = pf.total_return()

    # Handle both scalar and series just in case
    if hasattr(total_return, "item"):
        # For numpy scalar
        ret = float(total_return.item())
    elif hasattr(total_return, "iloc"):
        ret = float(total_return.iloc[0])
    else:
        ret = float(total_return)

    ret_pct = ret * 100

    # Rank the performance based on Total Return
    # Premium (>50%), Moderate (>=10%), and Low (<10%)
    print("\n--- Strategy Performance Ranking ---")

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
