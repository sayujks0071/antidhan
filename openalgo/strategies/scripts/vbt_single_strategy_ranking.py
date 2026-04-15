import vectorbt as vbt
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import requests

# Use curl_cffi for reliable yfinance downloads if available
try:
    from curl_cffi import requests as cffi_requests
    session = cffi_requests.Session(impersonate="chrome")
except ImportError:
    session = requests.Session()

def main():
    # Set up a single symbol
    symbol = "BTC-USD"

    print(f"Downloading data for {symbol}...")

    # Download data using vectorbt 0.28+ features
    data = vbt.YFData.download(
        symbol,
        period="1y",
        missing_index="drop",
        ticker_kwargs=dict(session=session)
    )
    price = data.get("Close")

    print("Running Dual SMA Crossover Backtest...")
    # Define SMA windows
    fast_window = 10
    slow_window = 50

    # Calculate MAs
    fast_ma = vbt.MA.run(price, fast_window)
    slow_ma = vbt.MA.run(price, slow_window)

    # Generate crossover signals
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Run portfolio backtest
    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        freq="1D"
    )

    # Calculate total return
    total_returns = pf.total_return()

    # Handle single-symbol metric vs multi-symbol
    # In a single symbol test, total_return() returns a scalar float
    if isinstance(total_returns, pd.Series):
        ret_val = total_returns.iloc[0]
    elif isinstance(total_returns, float):
        ret_val = total_returns
    else:
        # Fallback
        ret_val = float(total_returns)

    ret_pct = ret_val * 100

    # Rank the strategy
    # Premium, Moderate, or Low
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
