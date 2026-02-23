import vectorbt as vbt
import pandas as pd
import numpy as np

def run_strategy():
    print("Fetching data for BTC-USD using vectorbt...")
    # diverse kwargs to demonstrate new feature
    # Note: 'period' and 'interval' can also be passed directly to download
    # ticker_kwargs are passed to yfinance.Ticker
    try:
        data = vbt.YFData.download(
            "BTC-USD",
            period="max",
            missing_index="drop",
            ticker_kwargs={}
        )
    except Exception as e:
        print(f"Error downloading data: {e}")
        return

    price = data.get("Close")

    if price.empty:
        print("No data found.")
        return

    print(f"Data range: {price.index.min()} to {price.index.max()}")

    # Strategy: 10/50 SMA Crossover (Golden Cross)
    fast_ma_window = 10
    slow_ma_window = 50

    fast_ma = vbt.MA.run(price, fast_ma_window)
    slow_ma = vbt.MA.run(price, slow_ma_window)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Run Portfolio
    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=10000, freq='1D')

    # Get Stats
    stats = pf.stats()

    # metrics for ranking
    total_return_pct = pf.total_return() * 100
    sharpe_ratio = pf.sharpe_ratio()

    print("\n" + "="*50)
    print("STRATEGY PERFORMANCE METRICS")
    print("="*50)
    print(stats)
    print("\n" + "-"*50)

    # Classification Logic
    # Premium: Sharpe > 1.5 and Return > 50%
    # Moderate: Sharpe > 0.8 and Return > 0%
    # Low: All others

    rank = "Low"
    if sharpe_ratio > 1.5 and total_return_pct > 50:
        rank = "Premium"
    elif sharpe_ratio > 0.8 and total_return_pct > 0:
        rank = "Moderate"

    print(f"Total Return: {total_return_pct:.2f}%")
    print(f"Sharpe Ratio: {sharpe_ratio:.2f}")
    print(f"Strategy Rank: {rank}")
    print("-"*50)

if __name__ == "__main__":
    run_strategy()
