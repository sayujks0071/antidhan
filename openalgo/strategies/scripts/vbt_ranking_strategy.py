import vectorbt as vbt
import pandas as pd
import numpy as np

def run_strategy(symbol="BTC-USD"):
    """
    Runs a Dual SMA strategy on the given symbol using vectorbt.
    Ranks the strategy based on Sharpe Ratio and Total Return.
    """
    print(f"Running strategy for {symbol}...")

    # Use vectorbt 0.28+ feature: ticker_kwargs
    # We pass 'session': None to yfinance.Ticker via ticker_kwargs
    # This demonstrates the new capability to pass arguments directly to Ticker constructor
    try:
        data = vbt.YFData.download(
            symbol,
            period="2y",
            missing_index='drop',
            ticker_kwargs={"session": None}
        )
    except Exception as e:
        print(f"Error downloading data for {symbol}: {e}")
        return

    price = data.get("Close")

    if price.empty:
        print("No data found.")
        return

    # Strategy: Dual SMA (10, 20)
    fast_window = 10
    slow_window = 20

    fast_ma = vbt.MA.run(price, fast_window, short_name='fast')
    slow_ma = vbt.MA.run(price, slow_window, short_name='slow')

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Run Portfolio
    # freq='1D' is inferred from data usually, but good to be explicit if possible
    # In vbt 0.28, from_signals handles freq inference well
    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=100)

    # Extract Stats
    total_return = pf.total_return()
    sharpe_ratio = pf.sharpe_ratio()

    # Handle Series/Scalar output
    if isinstance(total_return, pd.Series):
        total_return = total_return.item()
    if isinstance(sharpe_ratio, pd.Series):
        sharpe_ratio = sharpe_ratio.item()

    # Convert to percentage
    total_return_pct = total_return * 100

    print("-" * 30)
    print(f"Backtest Results for {symbol}")
    print("-" * 30)
    print(f"Total Return: {total_return_pct:.2f}%")
    print(f"Sharpe Ratio: {sharpe_ratio:.2f}")

    # Ranking Logic
    # Premium: Sharpe > 1.5 and Return > 50%
    # Moderate: Sharpe > 0.8 and Return > 0%
    # Low: All others

    rank = "Low"
    if sharpe_ratio > 1.5 and total_return_pct > 50:
        rank = "Premium"
    elif sharpe_ratio > 0.8 and total_return_pct > 0:
        rank = "Moderate"

    print("-" * 30)
    print(f"Strategy Rank: {rank}")
    print("-" * 30)

if __name__ == "__main__":
    run_strategy()
