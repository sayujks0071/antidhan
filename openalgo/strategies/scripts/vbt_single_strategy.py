import vectorbt as vbt
import pandas as pd
import numpy as np
import warnings

# Suppress some warnings
warnings.filterwarnings("ignore")

def backtest_strategy(symbol="BTC-USD", fast_window=10, slow_window=50, start_date="2020-01-01"):
    """
    Backtests a Dual SMA strategy using vectorbt and ranks it.
    """
    print(f"Backtesting {symbol} with SMA({fast_window}, {slow_window}) since {start_date}...")

    try:
        # Download data using YFData
        # Note: In restricted environments, this might fail. We'll handle it.
        data = vbt.YFData.download(symbol, start=start_date, missing_index='drop')
        price = data.get("Close")
    except Exception as e:
        print(f"Error downloading data: {e}")
        print("Falling back to generated random data for demonstration.")
        np.random.seed(42)
        price = pd.Series(
            np.random.randn(1000).cumsum() + 100,
            index=pd.date_range(start=start_date, periods=1000)
        )

    if price.empty:
        print("No price data available.")
        return

    # Calculate indicators
    fast_ma = vbt.MA.run(price, fast_window, short_name="fast")
    slow_ma = vbt.MA.run(price, slow_window, short_name="slow")

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Create portfolio
    # init_cash=10000, fees=0.1%
    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        fees=0.001,
        freq="1D"
    )

    # Calculate stats
    total_return = pf.total_return()
    sharpe_ratio = pf.sharpe_ratio()
    max_drawdown = pf.max_drawdown()
    win_rate = pf.trades.win_rate()

    print("\n" + "=" * 30)
    print("BACKTEST RESULTS")
    print("=" * 30)
    print(f"Symbol:       {symbol}")
    print(f"Strategy:     SMA({fast_window}/{slow_window})")
    print("-" * 30)
    print(f"Total Return: {total_return:.2%}")
    print(f"Sharpe Ratio: {sharpe_ratio:.2f}")
    print(f"Max Drawdown: {max_drawdown:.2%}")
    print(f"Win Rate:     {win_rate:.2%}")
    print("-" * 30)

    # Ranking Logic
    # Premium: Sharpe > 1.5 AND Total Return > 50%
    # Moderate: Sharpe > 0.8 AND Total Return > 0%
    # Low: Otherwise

    rank = "Low"
    if sharpe_ratio > 1.5 and total_return > 0.5:
        rank = "Premium"
    elif sharpe_ratio > 0.8 and total_return > 0.0:
        rank = "Moderate"

    print(f"Strategy Rank: {rank}")
    print("=" * 30 + "\n")

    # Optional: Display Plotly chart if in interactive mode (but here we just return)
    # pf.plot().show()

    return rank

if __name__ == "__main__":
    backtest_strategy()
