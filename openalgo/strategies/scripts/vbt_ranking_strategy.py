import vectorbt as vbt
import pandas as pd
import numpy as np
import warnings

# Suppress specific warnings that might clutter output
warnings.filterwarnings("ignore")

def run_strategy_and_rank():
    print("Starting VectorBT Backtest & Ranking...")

    # 1. Download Data using ticker_kwargs (New in 0.28)
    # Using BTC-USD for demonstration as it's available 24/7 and standard for vbt examples
    # ticker_kwargs example: passing an empty dict or specific proxy args if needed
    print("Downloading data for BTC-USD...")
    try:
        # ticker_kwargs are passed to yfinance.Ticker class.
        # Valid args are 'session'. 'proxy' is not a valid arg for Ticker.__init__ in recent yfinance.
        data = vbt.YFData.download(
            "BTC-USD",
            period="2y",
            interval="1d",
            ticker_kwargs={"session": None}
        )
        price = data.get("Close")
    except Exception as e:
        print(f"Error downloading data: {e}")
        # Fallback to synthetic data if download fails (for robust testing environment)
        print("Falling back to synthetic data...")
        index = pd.date_range("2022-01-01", periods=730, freq="D")
        price = pd.Series(np.random.randn(730).cumsum() + 100, index=index, name="Close")

    # 2. Define Strategy (Dual SMA)
    fast_window = 10
    slow_window = 50

    print(f"Running Dual SMA Strategy ({fast_window}, {slow_window})...")
    fast_ma = vbt.MA.run(price, fast_window)
    slow_ma = vbt.MA.run(price, slow_window)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # 3. Backtest
    pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=10000, freq="1D")

    # 4. Extract Metrics
    total_return = pf.total_return() * 100 # percentage
    sharpe_ratio = pf.sharpe_ratio()

    print("-" * 30)
    print(f"Total Return: {total_return:.2f}%")
    print(f"Sharpe Ratio: {sharpe_ratio:.2f}")

    # 5. Ranking Logic
    # Premium: Sharpe > 1.5 and Return > 50%
    # Moderate: Sharpe > 0.8 and Return > 0%
    # Low: All others

    ranking = "Low"
    if sharpe_ratio > 1.5 and total_return > 50:
        ranking = "Premium"
    elif sharpe_ratio > 0.8 and total_return > 0:
        ranking = "Moderate"

    print(f"Strategy Ranking: {ranking}")
    print("-" * 30)

    # 6. Plot (Optional, but requested in features list "Plotly 6 support")
    try:
        fig = pf.plot()
        fig.write_html("backtest_plot.html")
        print("Performance plot saved to backtest_plot.html")
    except Exception as e:
        print(f"Could not save plot: {e}")

if __name__ == "__main__":
    try:
        run_strategy_and_rank()
    except Exception as e:
        print(f"Error running strategy: {e}")
        import traceback
        traceback.print_exc()
