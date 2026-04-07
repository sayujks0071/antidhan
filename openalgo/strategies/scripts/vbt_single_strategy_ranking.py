import vectorbt as vbt
import numpy as np

def main():
    # Set up a single symbol
    symbol = "BTC-USD"

    print(f"Downloading data for {symbol}...")

    # In vectorbt 0.28+, period is passed directly, ticker_kwargs takes valid Ticker parameters
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

    # In vectorbt 0.28+, backtesting a single symbol and parameterless strategy returns a scalar float
    if isinstance(total_return, (float, int, np.floating, np.integer)):
        ret_pct = float(total_return) * 100
    else:
        # Fallback just in case
        ret_pct = float(total_return.iloc[0]) * 100

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
