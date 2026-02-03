import json
import pandas as pd
import numpy as np
import glob
import os
import argparse
from datetime import datetime

# Default to current directory logs if not specified
DEFAULT_LOG_DIR = os.path.join(os.getcwd(), "openalgo_backup_20260128_164229", "logs")

def load_trades(log_dir):
    all_trades = []
    if not os.path.exists(log_dir):
        print(f"Log directory not found: {log_dir}")
        return pd.DataFrame()

    files = glob.glob(os.path.join(log_dir, "trades_*.json"))
    print(f"Found {len(files)} trade files in {log_dir}.")

    for f in files:
        strategy_name = os.path.basename(f).replace("trades_", "").replace(".json", "")
        try:
            with open(f, 'r') as file:
                trades = json.load(file)
                for t in trades:
                    t['strategy'] = strategy_name
                    # Parse timestamps
                    t['entry_time'] = pd.to_datetime(t['entry_time'])
                    t['exit_time'] = pd.to_datetime(t['exit_time'])
                    all_trades.append(t)
        except Exception as e:
            print(f"Error reading {f}: {e}")

    return pd.DataFrame(all_trades)

def analyze_correlation(df):
    print("\n## Cross-Strategy Correlation")
    if df.empty:
        print("No trades found.")
        return

    # Create a time series for each strategy
    # We will mark '1' for the minute of entry
    df['entry_minute'] = df['entry_time'].dt.floor('5min') # 5 min buckets

    pivot = df.pivot_table(index='entry_minute', columns='strategy', values='quantity', aggfunc='count').fillna(0)

    if pivot.empty or len(pivot.columns) < 2:
        print("Not enough strategies to calculate correlation.")
        return

    corr_matrix = pivot.corr()
    print(corr_matrix.to_markdown())

    # Check for high correlation
    high_corr_pairs = []
    strategies = corr_matrix.columns
    for i in range(len(strategies)):
        for j in range(i+1, len(strategies)):
            val = corr_matrix.iloc[i, j]
            if val > 0.7:
                pair = (strategies[i], strategies[j], val)
                high_corr_pairs.append(pair)
                print(f"**High Correlation Warning**: {strategies[i]} vs {strategies[j]} ({val:.2f})")

    return high_corr_pairs

def analyze_equity_curve(df):
    print("\n## Equity Curve Analysis")
    if df.empty: return

    # Sort by exit time (realized PnL)
    df = df.sort_values('exit_time')
    df['date'] = df['exit_time'].dt.date

    daily_pnl = df.groupby('date')['pnl'].sum()
    cumulative_pnl = daily_pnl.cumsum()

    print("\n### Daily PnL")
    print(daily_pnl.to_markdown())

    worst_day = daily_pnl.idxmin()
    worst_day_pnl = daily_pnl.min()

    print(f"\n**Worst Day**: {worst_day} (PnL: {worst_day_pnl:.2f})")

    # Drawdown Analysis
    running_max = cumulative_pnl.cummax()
    drawdown = cumulative_pnl - running_max
    max_drawdown = drawdown.min()

    print(f"**Max Drawdown**: {max_drawdown:.2f}")

    return worst_day

def strategy_performance(df):
    print("\n## Strategy Performance")
    if df.empty: return

    stats = []
    strategies = df['strategy'].unique()

    for strat in strategies:
        strat_df = df[df['strategy'] == strat].copy()
        strat_df = strat_df.sort_values('exit_time')

        total_pnl = strat_df['pnl'].sum()
        win_rate = len(strat_df[strat_df['pnl'] > 0]) / len(strat_df) * 100

        # Drawdown for this strategy
        strat_df['cum_pnl'] = strat_df['pnl'].cumsum()
        running_max = strat_df['cum_pnl'].cummax()
        dd = strat_df['cum_pnl'] - running_max
        max_dd = dd.min()

        # Calmar Ratio (Simple: Total PnL / Max DD). Handle 0 DD.
        if max_dd == 0:
            calmar = float('inf') if total_pnl > 0 else 0
        else:
            calmar = abs(total_pnl / max_dd)

        stats.append({
            'Strategy': strat,
            'Total PnL': total_pnl,
            'Win Rate (%)': win_rate,
            'Max Drawdown': max_dd,
            'Calmar Ratio': calmar
        })

    stats_df = pd.DataFrame(stats).sort_values('Calmar Ratio', ascending=False)
    print(stats_df.to_markdown(index=False))

def main():
    parser = argparse.ArgumentParser(description="System Audit Tool")
    parser.add_argument("--logs", type=str, default=DEFAULT_LOG_DIR, help="Path to logs directory")
    args = parser.parse_args()

    df = load_trades(args.logs)
    analyze_correlation(df)
    analyze_equity_curve(df)
    strategy_performance(df)

if __name__ == "__main__":
    main()
