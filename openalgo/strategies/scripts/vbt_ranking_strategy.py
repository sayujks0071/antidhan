import vectorbt as vbt
import pandas as pd
import numpy as np

def run_strategy():
    print("Downloading data for BTC-USD...")
    # New in 0.28: ticker_kwargs passed to yfinance.Ticker
    # We use it to demonstrate the feature as requested.
    data = vbt.YFData.download("BTC-USD", ticker_kwargs={})

    price = data.get("Close")

    if price.empty:
        print("No data downloaded.")
        return

    # Strategy: Dual SMA (10, 50)
    print("Running Dual SMA (10, 50) Strategy...")
    fast_ma = vbt.MA.run(price, 10)
    slow_ma = vbt.MA.run(price, 50)
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Backtest
    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=100)

    # Calculate stats
    total_return_raw = pf.total_return()
    if isinstance(total_return_raw, pd.Series):
        total_return_raw = total_return_raw.iloc[0]

    total_return_pct = float(total_return_raw) * 100

    sharpe_ratio = pf.sharpe_ratio()
    if isinstance(sharpe_ratio, pd.Series):
        sharpe_ratio = sharpe_ratio.iloc[0]

    sharpe_ratio = float(sharpe_ratio)

    print(f"Total Return: {total_return_pct:.2f}%")
    print(f"Sharpe Ratio: {sharpe_ratio:.2f}")

    # Ranking logic
    # Premium: Sharpe > 1.5 and Return > 50%
    # Moderate: Sharpe > 0.8 and Return > 0%
    # Low: All others.

    if sharpe_ratio > 1.5 and total_return_pct > 50:
        rank = "Premium"
    elif sharpe_ratio > 0.8 and total_return_pct > 0:
        rank = "Moderate"
    else:
        rank = "Low"

    print(f"Strategy Rank: {rank}")

if __name__ == "__main__":
    try:
        run_strategy()
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
