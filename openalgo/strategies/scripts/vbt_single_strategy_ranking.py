import vectorbt as vbt
import numpy as np

def main():
    # Backtest a single strategy and rank it based on Total Return
    symbol = "BTC-USD"
    print(f"Downloading data for {symbol}...")

    # VectorBT 0.28+ uses period argument directly and ticker_kwargs for initialization parameters
    data = vbt.YFData.download(
        symbol,
        period="1y",
        missing_index="drop",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    print("Running Dual SMA Crossover Backtest for a single symbol...")
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

    # In VectorBT 0.28+ when there's a single symbol and no hyperparameter grid,
    # total_return might be a scalar float instead of a pd.Series
    if isinstance(total_return, (int, float, np.number)):
        val = float(total_return)
    else:
        # Fallback if it's a pandas object
        try:
            val = float(total_return.iloc[0])
        except (AttributeError, IndexError):
            val = float(total_return)

    ret_pct = val * 100

    # Rank the performance based on Total Return
    # Premium (>50%), Moderate (10-50%), and Low (<10%)
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
