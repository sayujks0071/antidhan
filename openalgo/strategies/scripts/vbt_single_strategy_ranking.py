import vectorbt as vbt
import numpy as np
import pandas as pd
import argparse
import sys
import os

# Ensure the root directory and utils are in path
strategies_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = os.path.dirname(strategies_dir)
sys.path.insert(0, root_dir)

def main():
    parser = argparse.ArgumentParser(description='Run VectorBT backtest on a single symbol.')
    parser.add_argument('--symbol', type=str, default='BTC-USD', help='Symbol to backtest')
    parser.add_argument('--period', type=str, default='1y', help='Time period for backtest')

    # Handle the fact that OpenAlgo platform does not pass CLI arguments well,
    # but since this is a utility script, we allow them or fallback to defaults
    try:
        args = parser.parse_args()
    except SystemExit:
        # Provide defaults if run in a restricted environment
        class Args:
            pass
        args = Args()
        args.symbol = 'BTC-USD'
        args.period = '1y'

    symbol = args.symbol
    print(f"Downloading data for {symbol}...")

    # yf.Ticker in newer versions accepts 'session' parameter
    data = vbt.YFData.download(
        symbol,
        period=args.period,
        missing_index="drop",
        ticker_kwargs={"session": None}
    )
    price = data.get("Close")

    print(f"Running Dual SMA Crossover Backtest for {symbol}...")
    fast_window = 10
    slow_window = 50

    fast_ma = vbt.MA.run(price, fast_window)
    slow_ma = vbt.MA.run(price, slow_window)

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    pf = vbt.Portfolio.from_signals(
        price,
        entries,
        exits,
        init_cash=10000,
        freq="1D"
    )

    total_return = pf.total_return()

    # Handle scalar return values natively for parameterless indicators
    if isinstance(total_return, pd.Series):
        if isinstance(total_return.index, pd.MultiIndex):
            try:
                ret = total_return.xs(symbol, level='symbol').iloc[0]
            except Exception:
                for idx_tuple, value in total_return.items():
                    if idx_tuple[-1] == symbol:
                        ret = value
                        break
        else:
            ret = total_return[symbol]
    else:
        # Scalar return value
        ret = total_return

    ret_pct = ret * 100

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
