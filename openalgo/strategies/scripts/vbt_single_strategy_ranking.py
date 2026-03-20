import vectorbt as vbt
import pandas_ta_classic as ta
import numpy as np

def main():
    # Single symbol and strategy
    symbol = "BTC-USD"
    print(f"Downloading data for {symbol}...")

    # VectorBT 0.28+ features:
    # 1. period is passed directly to download
    # 2. ticker_kwargs is used for yfinance.Ticker parameters
    data = vbt.YFData.download(
        symbol,
        period="1y",
        missing_index="drop",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    # We can use pandas_ta_classic as well, to show fixed dependency
    # For example, let's use it to get SMA, though vbt has its own MA.
    # price_df = price.to_frame()
    # price_df.ta.sma(length=10, append=True)

    # Simple strategy: 10-day SMA crossed above 50-day SMA
    fast_ma = vbt.MA.run(price, 10)
    slow_ma = vbt.MA.run(price, 50)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # freq="1D" is required
    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=10000, freq="1D")

    # Calculate performance metrics
    total_returns = pf.total_return()

    # For a single symbol and single parameter, total_return is typically a scalar
    if hasattr(total_returns, "item"):
        ret_val = total_returns.item()
    elif isinstance(total_returns, (float, int)):
        ret_val = total_returns
    else:
        ret_val = float(total_returns.iloc[0] if hasattr(total_returns, "iloc") else total_returns)

    ret_pct = ret_val * 100

    # Rank total return as Premium (>50%), Moderate (>=10%), or Low (<10%)
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

if __name__ == "__main__":
    main()
