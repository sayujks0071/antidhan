"""
VectorBT Ranking Strategy
Uses VectorBT 0.28+ to backtest a Dual SMA strategy and rank it.
"""
import vectorbt as vbt
import pandas as pd
import numpy as np

def run_strategy(symbol="BTC-USD", fast_window=10, slow_window=50, period="2y"):
    """
    Backtests a Dual SMA strategy and ranks it.

    Args:
        symbol (str): The ticker symbol to backtest.
        fast_window (int): Fast SMA window.
        slow_window (int): Slow SMA window.
        period (str): Period to download data for.

    Returns:
        dict: A dictionary containing metrics and the rank.
    """
    print(f"Downloading data for {symbol}...")

    # ticker_kwargs is a new feature in vbt 0.28 passed to yfinance.Ticker
    data = vbt.YFData.download(
        symbol,
        missing_index='drop',
        period=period,
        ticker_kwargs={}
    )

    price = data.get("Close")

    # In vbt, price is a wrapper. To check for emptiness, we might need to access the underlying pandas object
    # or just proceed. If empty, vbt usually raises or returns empty series.
    if price.shape[0] == 0:
        print("No data found.")
        return None

    # Calculate indicators
    fast_ma = vbt.MA.run(price, fast_window)
    slow_ma = vbt.MA.run(price, slow_window)

    # Generate signals
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Run Portfolio
    # freq='D' assumes daily data for annualization (252 days)
    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=10000, freq='D')

    # Extract metrics
    total_return = pf.total_return() * 100 # Convert to percentage
    sharpe_ratio = pf.sharpe_ratio()

    # Handle NaN sharpe (e.g. no trades)
    if np.isnan(sharpe_ratio):
        sharpe_ratio = 0.0

    # Rank Strategy
    if sharpe_ratio > 1.5 and total_return > 50:
        rank = "Premium"
    elif sharpe_ratio > 0.8 and total_return > 0:
        rank = "Moderate"
    else:
        rank = "Low"

    result = {
        "Symbol": symbol,
        "Fast MA": fast_window,
        "Slow MA": slow_window,
        "Total Return [%]": total_return,
        "Sharpe Ratio": sharpe_ratio,
        "Rank": rank
    }

    return result

if __name__ == "__main__":
    try:
        metrics = run_strategy("BTC-USD")
        if metrics:
            print("\nStrategy Results:")
            print("-" * 30)
            for k, v in metrics.items():
                if isinstance(v, float):
                    print(f"{k}: {v:.2f}")
                else:
                    print(f"{k}: {v}")
            print("-" * 30)
    except Exception as e:
        print(f"Error running strategy: {e}")
