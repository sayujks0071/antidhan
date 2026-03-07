import vectorbt as vbt
import pandas as pd

def main():
    symbol = "BTC-USD"
    print(f"Downloading data for {symbol}...")

    data = vbt.YFData.download(
        symbol,
        period="1y",
        missing_index="drop",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    print("Running Dual SMA Crossover Backtest...")
    fast_ma = vbt.MA.run(price, 10)
    slow_ma = vbt.MA.run(price, 50)
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        freq="1D"
    )

    total_returns = pf.total_return()

    print("\n--- Strategy Performance Ranking ---")
    if hasattr(total_returns, "index"):
        # Not a scalar
        val = total_returns.iloc[0] if len(total_returns) > 0 else 0
    else:
        # Scalar
        val = total_returns

    ret_pct = val * 100

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
