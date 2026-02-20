import vectorbt as vbt
import numpy as np
import pandas as pd
import sys
import os

def backtest_and_rank(symbol='BTC-USD', start='2020-01-01', end='2023-01-01'):
    """
    Backtests an SMA Crossover strategy using vectorbt (v0.28+).
    Optimizes parameters and ranks the best result.
    """
    print(f"Starting backtest for {symbol} from {start} to {end}...")

    # 1. Download Data
    try:
        # Utilizing vectorbt's YFData
        data = vbt.YFData.download(symbol, start=start, end=end, missing_index='drop')
        price = data.get("Close")
    except Exception as e:
        print(f"Error downloading data for {symbol}: {e}")
        print("Attempting to generate random data for demonstration...")
        # Generate random data if download fails (fallback)
        np.random.seed(42)
        dates = pd.date_range(start=start, periods=1000, freq='D')
        # Random walk
        returns = np.random.normal(0.001, 0.02, len(dates))
        price_values = 100 * np.cumprod(1 + returns)
        price = pd.Series(price_values, index=dates, name='Close')

    if price.empty:
        print("No price data available.")
        return

    print(f"Data loaded: {len(price)} records.")

    # 2. Strategy: Dual SMA Crossover Optimization
    # We test all combinations of windows from 10 to 100 with step 5
    print("Running optimization for SMA Crossover...")

    windows = np.arange(10, 101, 5)

    # fast_ma and slow_ma are broadcasted arrays of MAs
    # run_combs(r=2) generates all pairs (window1, window2) where window1 < window2 usually?
    # Actually run_combs returns combinations. We treat the first as fast, second as slow.
    fast_ma, slow_ma = vbt.MA.run_combs(price, window=windows, r=2, short_names=['fast', 'slow'])

    # Generate signals
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # Run Portfolio
    # init_cash=10000, fees=0.1% (0.001)
    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        fees=0.001,
        freq='1D'
    )

    # 3. Find Best Strategy
    # We use Sharpe Ratio as the optimization metric
    try:
        sharpe_ratios = pf.sharpe_ratio()
        best_idx = sharpe_ratios.idxmax()
        best_pf = pf[best_idx]
    except Exception as e:
        print(f"Error finding best strategy: {e}")
        # Fallback to the first one if optimization result extraction fails
        best_pf = pf.iloc[0]
        best_idx = (windows[0], windows[1])

    print(f"Best Configuration: Fast={best_idx[0]}, Slow={best_idx[1]}")

    # 4. Extract Metrics
    total_return = best_pf.total_return() * 100
    sharpe = best_pf.sharpe_ratio()
    max_dd = best_pf.max_drawdown() * 100
    win_rate = best_pf.trades.win_rate() * 100

    print("\n--- Backtest Results ---")
    print(f"Total Return: {total_return:.2f}%")
    print(f"Sharpe Ratio: {sharpe:.2f}")
    print(f"Max Drawdown: {max_dd:.2f}%")
    print(f"Win Rate:     {win_rate:.2f}%")
    print("------------------------")

    # 5. Ranking Logic
    ranking = "Low"
    if sharpe > 1.5 and total_return > 50:
        ranking = "Premium"
    elif sharpe > 0.8 and total_return > 10:
        ranking = "Moderate"

    print(f"\nStrategy Rank: {ranking}")

    # 6. Visualization
    output_file = os.path.join(os.path.dirname(__file__), "vbt_backtest_result.html")
    try:
        # Plotting the portfolio
        fig = best_pf.plot()

        # Add title using layout update
        fig.update_layout(title_text=f"Best SMA Crossover ({best_idx[0]}/{best_idx[1]}) - Rank: {ranking}")

        fig.write_html(output_file)
        print(f"Plot saved to: {output_file}")
    except Exception as e:
        print(f"Error saving plot: {e}")

if __name__ == "__main__":
    backtest_and_rank()
