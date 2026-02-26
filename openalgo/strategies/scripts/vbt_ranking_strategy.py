"""
VectorBT Ranking Strategy
Description: Backtests a Dual SMA strategy and ranks it (Premium/Moderate/Low) using VectorBT 0.28+ features.
             Demonstrates ticker_kwargs in YFData and Plotly 6 support.
"""

import vectorbt as vbt
import numpy as np
import pandas as pd
import yfinance as yf
import traceback

def rank_strategy(stats):
    """
    Ranks the strategy based on Sharpe Ratio and Total Return.
    Criteria:
    - Premium: Sharpe > 1.5 and Return > 50%
    - Moderate: Sharpe > 0.8 and Return > 0%
    - Low: All others
    """
    sharpe = stats.get('Sharpe Ratio', 0)
    total_return = stats.get('Total Return [%]', 0)

    # Handle potential NaN or None
    if pd.isna(sharpe): sharpe = -np.inf
    if pd.isna(total_return): total_return = -np.inf

    if sharpe > 1.5 and total_return > 50:
        return "Premium"
    elif sharpe > 0.8 and total_return > 0:
        return "Moderate"
    else:
        return "Low"

def run_backtest(symbol="BTC-USD"):
    print(f"Running backtest for {symbol}...")

    # 1. Data Download with fallback and ticker_kwargs
    try:
        print(f"Attempting to download data for {symbol} using vbt.YFData with ticker_kwargs...")
        # demonstrating ticker_kwargs - passed to yfinance.Ticker
        # We'll pass a harmless kwarg just to show usage, e.g., skipping scraping if applicable or just empty
        # Real use case: proxy=... or session=...
        data = vbt.YFData.download(
            symbol,
            period="1y",
            missing_index='drop',
            ticker_kwargs={}
        )
        price = data.get("Close")
        if price.empty:
            raise ValueError("Downloaded data is empty.")
        print("Data download successful.")

    except Exception as e:
        print(f"Data download failed or yfinance not available: {e}")
        print("Falling back to synthetic data generation.")
        # Generate synthetic data
        np.random.seed(42)
        index = pd.date_range(start='2023-01-01', periods=365, freq='D')
        # Random walk
        returns = np.random.normal(loc=0.001, scale=0.02, size=365)
        price_values = 100 * np.cumprod(1 + returns)
        price = pd.Series(price_values, index=index, name='Close')

    # 2. Strategy Logic: Dual SMA
    # Fast SMA: 10, Slow SMA: 50
    fast_ma = vbt.MA.run(price, 10, short_name='fast')
    slow_ma = vbt.MA.run(price, 50, short_name='slow')

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    # 3. Portfolio Construction
    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        fees=0.001, # 0.1%
        freq='1D'
    )

    # 4. Stats and Ranking
    stats = pf.stats()
    rank = rank_strategy(stats)

    print("\n" + "="*40)
    print(f"Strategy Ranking: {rank.upper()}")
    print("="*40)
    print(stats)

    # 5. Plotting (demonstrating Plotly 6 support via vbt)
    # Using 'show_legend' as 'showlegend' in some contexts, but vbt handles standard plotly args
    try:
        print("\nGenerating plot...")
        # We return the figure object so it can be shown or saved
        fig = pf.plot()
        # In a headless environment, we might not see it, but we can verify it was created
        # If running locally, fig.show() would open it.
        # We can save it to a file
        output_file = f"vbt_backtest_{symbol}_{rank}.html"
        fig.write_html(output_file)
        print(f"Plot saved to {output_file}")
    except Exception as e:
        print(f"Plotting failed: {e}")
        traceback.print_exc()

    return rank, stats

if __name__ == "__main__":
    # Allow passing symbol via CLI args if needed, but defaulting to BTC-USD
    run_backtest("BTC-USD")
