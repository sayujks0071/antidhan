#!/usr/bin/env python3
"""
VectorBT Ranking Strategy
=========================

This script demonstrates using vectorbt (v0.28+) to backtest a simple strategy
and rank it based on performance metrics.

Features shown:
- vbt.YFData.download with ticker_kwargs (new in 0.28)
- Portfolio simulation
- Ranking logic (Premium, Moderate, Low)
- Plotting (saved to HTML)

Usage:
    python vbt_ranking_strategy.py
"""

import vectorbt as vbt
import pandas as pd
import numpy as np
import warnings

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore")

def run_backtest(symbol="BTC-USD", fast_window=10, slow_window=50, start_date="2020-01-01", end_date="2024-01-01"):
    """
    Runs a simple Dual SMA backtest and ranks the strategy.
    """
    print(f"\nRunning Backtest for {symbol}...")
    print(f"Strategy: Dual SMA ({fast_window}/{slow_window})")
    print(f"Period: {start_date} to {end_date}")

    # 1. Download Data using vbt.YFData with ticker_kwargs (New in 0.28)
    # ticker_kwargs are passed to yfinance.Ticker
    print("Downloading data...")
    try:
        data = vbt.YFData.download(
            symbol,
            start=start_date,
            end=end_date,
            missing_index='drop',
            # ticker_kwargs are passed to yfinance.Ticker
            # We use an empty dict here but one could pass 'session' or other Ticker args
            ticker_kwargs={}
        )
        price = data.get("Close")
    except Exception as e:
        print(f"Error downloading data: {e}")
        return

    if price.empty:
        print("No data found.")
        return

    # 2. Define Strategy (Dual SMA Crossover)
    fast_ma = vbt.MA.run(price, fast_window)
    slow_ma = vbt.MA.run(price, slow_window)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # 3. Run Portfolio
    # assuming $10,000 initial capital, 0.1% fees
    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        fees=0.001,
        freq="1D"
    )

    # 4. Calculate Stats
    total_return = pf.total_return()
    sharpe_ratio = pf.sharpe_ratio()
    max_drawdown = pf.max_drawdown()

    # Benchmark (Buy and Hold)
    benchmark_return = (price.iloc[-1] - price.iloc[0]) / price.iloc[0]

    print("\n--- Results ---")
    print(f"Total Return: {total_return * 100:.2f}%")
    print(f"Benchmark Return: {benchmark_return * 100:.2f}%")
    print(f"Sharpe Ratio: {sharpe_ratio:.4f}")
    print(f"Max Drawdown: {max_drawdown * 100:.2f}%")

    # 5. Rank Strategy
    rank = "Low"
    if total_return > 0:
        if sharpe_ratio > 1.0 and total_return > benchmark_return:
            rank = "Premium"
        elif sharpe_ratio > 0.5:
            rank = "Moderate"
        else:
            rank = "Low" # Positive return but poor risk-adjusted
    else:
        rank = "Low"

    print(f"\n>>> STRATEGY RANK: {rank} <<<")

    # 6. Plotting
    # Saving to HTML as we are in a headless environment
    try:
        output_file = "vbt_ranking_strategy.html"
        pf.plot().write_html(output_file)
        print(f"\nPlot saved to {output_file}")
    except Exception as e:
        print(f"Could not generate plot: {e}")

if __name__ == "__main__":
    # Example run
    run_backtest("BTC-USD", fast_window=10, slow_window=50)

    # You can try other symbols if you have yfinance installed and internet access
    # run_backtest("AAPL", fast_window=20, slow_window=50)
