import vectorbt as vbt
import pandas as pd
import numpy as np
import yfinance as yf
# Attempt to import pandas_ta_classic if needed
try:
    import pandas_ta_classic as ta
except ImportError:
    pass

def rank_strategy_performance(total_return_pct):
    """
    Ranks strategy total return as Premium, Moderate, or Low.
    Return values are expected to be scalar floats representing the percentage return (e.g., 55.0 for 55%).
    """
    if total_return_pct > 50.0:
        return "Premium"
    elif total_return_pct >= 10.0:
        return "Moderate"
    else:
        return "Low"

def main():
    print("Running VectorBT Single Strategy Ranking Backtest...")

    # Configuration
    symbol = "BTC-USD"
    # Download data
    print(f"Downloading data for {symbol}...")
    data = vbt.YFData.download(symbol, period="1y")
    price = data.get("Close")

    if price is None or len(price) == 0:
        print("Error: No data retrieved.")
        return

    print("Running Dual-SMA Crossover Strategy...")
    # Dual-SMA crossover parameters
    fast_window = 10
    slow_window = 50

    # Calculate indicators
    fast_ma = vbt.MA.run(price, window=fast_window)
    slow_ma = vbt.MA.run(price, window=slow_window)

    # Generate signals
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Run portfolio backtest
    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=100)

    # Extract scalar native return values natively for parameterless indicators
    # Note: Using total_return() returns the raw decimal (e.g. 0.55 for 55%)
    # In VBT 0.28+, pf.total_return() might return a float if there are no parameters
    raw_return = pf.total_return()

    # Handle scalar or Series
    if isinstance(raw_return, pd.Series):
        if len(raw_return) == 1:
            raw_return = raw_return.iloc[0]
        else:
            print("Warning: total_return is a Series with multiple elements. Taking the first.")
            raw_return = raw_return.iloc[0]

    total_return_pct = raw_return * 100.0

    # Rank the return
    rank = rank_strategy_performance(total_return_pct)

    print("-" * 30)
    print(f"Symbol: {symbol}")
    print(f"Total Return: {total_return_pct:.2f}%")
    print(f"Strategy Rank: {rank}")
    print("-" * 30)

if __name__ == "__main__":
    main()
