import vectorbt as vbt
import numpy as np

def main():
    symbol = "BTC-USD"
    print(f"Downloading data for {symbol}...")

    # Download data with vectorbt 0.28+ API
    data = vbt.YFData.download(
        symbol,
        period="1y",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    print("Running Dual SMA Crossover Backtest...")
    fast_ma = vbt.MA.run(price, 10)
    slow_ma = vbt.MA.run(price, 50)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Run portfolio
    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=10000, freq="1D")

    # Calculate performance metrics
    total_returns = pf.total_return()

    # In vectorbt 0.28+, pf.total_return() returns a single numpy scalar for a single symbol
    if isinstance(total_returns, (float, int, np.number)):
        ret_pct = float(total_returns) * 100
    else:
        ret_pct = float(total_returns.iloc[0]) * 100

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
