"""
VectorBT 0.28+ Ranking Strategy
Demonstrates backtesting, ranking, and new features (Plotly 6 support, ticker_kwargs).
"""
import vectorbt as vbt
import pandas as pd
import numpy as np

def run_strategy():
    print("Fetching data for ^NSEI (Nifty 50) using vectorbt 0.28+...")

    # New in 0.28: ticker_kwargs passed to yfinance.Ticker
    # We demonstrate using ticker_kwargs (though empty here as defaults are fine)
    try:
        data = vbt.YFData.download(
            "^NSEI",
            start="2020-01-01",
            missing_index='drop',
            ticker_kwargs={}
        )
    except Exception as e:
        print(f"Error downloading data: {e}")
        return

    price = data.get("Close")

    if price.empty:
        print("No data fetched.")
        return

    print(f"Data fetched: {len(price)} bars.")

    # Strategy: Dual SMA Crossover
    fast_window = 10
    slow_window = 50

    print(f"Running Dual SMA Strategy ({fast_window}, {slow_window})...")

    fast_ma = vbt.MA.run(price, fast_window)
    slow_ma = vbt.MA.run(price, slow_window)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=100000, freq='1D')

    # Calculate Metrics
    sharpe = pf.sharpe_ratio()
    total_return_pct = pf.total_return() * 100

    print(f"Sharpe Ratio: {sharpe:.4f}")
    print(f"Total Return: {total_return_pct:.2f}%")

    # Ranking Logic
    rank = "Low"
    if sharpe > 1.5 and total_return_pct > 50:
        rank = "Premium"
    elif sharpe > 0.8 and total_return_pct > 0:
        rank = "Moderate"

    print("-" * 30)
    print(f"STRATEGY RANK: {rank}")
    print("-" * 30)

    # Demonstrating Plotly 6 support integration
    try:
        # Just generate the figure to ensure compatibility
        fig = pf.plot()
        # fig.show() # Skipped in headless environment
    except Exception as e:
        print(f"Plotting error (Plotly 6 check): {e}")

if __name__ == "__main__":
    run_strategy()
