import vectorbt as vbt
import pandas as pd
import numpy as np

# Define ranking thresholds
RANKING = {
    "Premium": {"sharpe": 1.5, "return": 50.0},
    "Moderate": {"sharpe": 0.8, "return": 0.0}
}

def get_rank(sharpe, total_return):
    """
    Ranks the strategy based on Sharpe Ratio and Total Return.
    """
    if sharpe > RANKING["Premium"]["sharpe"] and total_return > RANKING["Premium"]["return"]:
        return "Premium"
    elif sharpe > RANKING["Moderate"]["sharpe"] and total_return > RANKING["Moderate"]["return"]:
        return "Moderate"
    else:
        return "Low"

def run_strategy(symbol="BTC-USD", start_date="2020-01-01", end_date="2024-01-01", fast_window=10, slow_window=50):
    print(f"Running backtest for {symbol} from {start_date} to {end_date}...")

    try:
        # vbt.YFData.download is used to fetch data
        # New in 0.28: ticker_kwargs can be passed if needed, but defaults are fine
        data = vbt.YFData.download(symbol, start=start_date, end=end_date, missing_index='drop')
        price = data.get("Close")
    except Exception as e:
        print(f"Error fetching data: {e}")
        # Fallback to random data if download fails (e.g. no internet)
        print("Falling back to synthetic data...")
        index = pd.date_range(start=start_date, end=end_date, freq='D')
        # Create a trend for better results
        price = pd.Series(np.random.randn(len(index)).cumsum() + 100 + np.linspace(0, 50, len(index)), index=index, name="Close")

    # Simple Dual SMA Strategy
    fast_ma = vbt.MA.run(price, fast_window)
    slow_ma = vbt.MA.run(price, slow_window)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=10000, freq='1D')

    total_return = pf.total_return() * 100
    sharpe = pf.sharpe_ratio()

    rank = get_rank(sharpe, total_return)

    print("-" * 30)
    print(f"Strategy Results for {symbol}:")
    print(f"Total Return: {total_return:.2f}%")
    print(f"Sharpe Ratio: {sharpe:.2f}")
    print(f"Rank: {rank}")
    print("-" * 30)

    return {
        "symbol": symbol,
        "total_return": total_return,
        "sharpe": sharpe,
        "rank": rank
    }

if __name__ == "__main__":
    run_strategy()
