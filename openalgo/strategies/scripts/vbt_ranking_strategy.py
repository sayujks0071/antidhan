"""
CHANGELOG:
- 2024-05-20: Created vbt_ranking_strategy.py using VectorBT 0.28+ features.
"""

import sys
import os
import argparse
import pandas as pd
import numpy as np

try:
    import vectorbt as vbt
except ImportError:
    print("vectorbt is not installed. Please install it using 'pip install vectorbt yfinance plotly'")
    sys.exit(1)

def run_backtest(symbol="SPY", fast_window=10, slow_window=50, start_date=None, end_date=None):
    """
    Runs a backtest using a Dual SMA strategy and ranks the strategy performance.
    """
    print(f"Downloading data for {symbol}...")

    # Using ticker_kwargs in YFData as available in VectorBT 0.28+
    ticker_kwargs = {}
    if start_date:
        ticker_kwargs['start'] = start_date
    if end_date:
        ticker_kwargs['end'] = end_date

    data = vbt.YFData.download(
        symbol,
        missing_index="drop",
        ticker_kwargs=ticker_kwargs
    )

    price = data.get("Close")

    if price is None or price.empty:
        print(f"Error: Could not retrieve price data for {symbol}.")
        return None

    print(f"Running Dual SMA strategy (Fast: {fast_window}, Slow: {slow_window})...")
    fast_ma = vbt.MA.run(price, fast_window)
    slow_ma = vbt.MA.run(price, slow_window)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=10000, fees=0.001, freq="1D")

    stats = pf.stats()
    total_return = stats.get("Total Return [%]", 0.0)

    if pd.isna(total_return):
        total_return = 0.0

    # Rank performance
    if total_return > 50:
        rank = "Premium"
    elif total_return >= 10:
        rank = "Moderate"
    else:
        rank = "Low"

    print(f"\n--- Strategy Performance: {rank} ---")
    print(f"Total Return: {total_return:.2f}%")
    print(f"Win Rate: {stats.get('Win Rate [%]', 0.0):.2f}%")
    print(f"Max Drawdown: {stats.get('Max Drawdown [%]', 0.0):.2f}%")
    print(f"Profit Factor: {stats.get('Profit Factor', 0.0):.2f}")

    return {
        "portfolio": pf,
        "stats": stats,
        "rank": rank,
        "total_return": total_return
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VectorBT Ranking Strategy")
    parser.add_argument("--symbol", type=str, default="SPY", help="Symbol to backtest")
    parser.add_argument("--fast", type=int, default=10, help="Fast SMA window")
    parser.add_argument("--slow", type=int, default=50, help="Slow SMA window")
    parser.add_argument("--plot", action="store_true", help="Save plot as HTML")

    args = parser.parse_args()

    result = run_backtest(symbol=args.symbol, fast_window=args.fast, slow_window=args.slow)

    if result and args.plot:
        pf = result["portfolio"]
        fig = pf.plot()
        filename = f"{args.symbol}_vbt_plot.html"
        fig.write_html(filename)
        print(f"\nSaved plot to {filename}")
