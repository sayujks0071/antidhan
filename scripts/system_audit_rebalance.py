import json
import os
import glob
import argparse
import pandas as pd
import numpy as np
from datetime import datetime

DEFAULT_LOG_DIR = "openalgo_backup_20260128_164229/logs/"
OUTPUT_FILE = "audit_results.md"

def load_trades(log_dir):
    all_trades = []

    # Check if generic logs dir exists if default not found
    if not os.path.exists(log_dir) and os.path.exists("logs/"):
        log_dir = "logs/"

    # Find all trades_*.json files
    files = glob.glob(os.path.join(log_dir, "trades_*.json"))

    if not files:
        print(f"No trade logs found in {log_dir}")
        return pd.DataFrame()

    print(f"Loading trades from {log_dir}...")

    for f in files:
        strategy_name = os.path.basename(f).replace("trades_", "").replace(".json", "")
        try:
            with open(f, 'r') as file:
                data = json.load(file)
                # If data is a list of trades
                if isinstance(data, list):
                    for trade in data:
                        trade['strategy'] = strategy_name
                        all_trades.append(trade)
        except Exception as e:
            print(f"Error reading {f}: {e}")

    if not all_trades:
        return pd.DataFrame()

    df = pd.DataFrame(all_trades)

    # Convert timestamps
    if 'entry_time' in df.columns:
        df['entry_time'] = pd.to_datetime(df['entry_time'])
    if 'exit_time' in df.columns:
        df['exit_time'] = pd.to_datetime(df['exit_time'])

    return df

def analyze_correlation(df):
    if df.empty:
        return "No trades to analyze.", []

    # Create a daily PnL series for each strategy
    # We use exit_time for PnL realization
    df['date'] = df['exit_time'].dt.date

    pivot_pnl = df.pivot_table(index='date', columns='strategy', values='pnl', aggfunc='sum').fillna(0)

    if pivot_pnl.empty or len(pivot_pnl.columns) < 2:
        return "Not enough data/strategies for correlation analysis.", []

    correlation_matrix = pivot_pnl.corr()

    # Check for correlations > 0.7
    high_corr_pairs = []

    strategies = correlation_matrix.columns
    for i in range(len(strategies)):
        for j in range(i+1, len(strategies)):
            s1 = strategies[i]
            s2 = strategies[j]
            corr = correlation_matrix.iloc[i, j]
            if corr > 0.7:
                high_corr_pairs.append((s1, s2, corr))

    result_md = "## Cross-Strategy Correlation\n\n"
    result_md += "Correlation Matrix:\n\n"
    result_md += correlation_matrix.to_markdown() + "\n\n"

    if high_corr_pairs:
        result_md += "### Highly Correlated Pairs (> 0.7)\n"
        for s1, s2, corr in high_corr_pairs:
            result_md += f"- **{s1}** and **{s2}**: {corr:.2f}\n"
            result_md += f"  - Recommendation: Merge into 'Hybrid' strategy or keep the one with higher Calmar Ratio.\n"
    else:
        result_md += "No highly correlated pairs found.\n"

    return result_md, high_corr_pairs

def stress_test_equity_curve(df):
    if df.empty:
        return "No trades for stress test."

    # Sort by exit time
    df = df.sort_values('exit_time')

    # Group by date for portfolio daily PnL
    df['date'] = df['exit_time'].dt.date
    daily_pnl = df.groupby('date')['pnl'].sum()

    # Calculate Cumulative PnL (Equity Curve)
    equity_curve = daily_pnl.cumsum()

    # Identify Worst Day
    worst_day_date = daily_pnl.idxmin()
    worst_day_pnl = daily_pnl.min()

    # Get trades for the worst day
    worst_day_trades = df[df['date'] == worst_day_date]

    result_md = "## Equity Curve Stress Test\n\n"
    result_md += f"- **Worst Day**: {worst_day_date}\n"
    result_md += f"- **Loss**: {worst_day_pnl:.2f}\n\n"

    result_md += "### Trades on Worst Day\n"
    result_md += worst_day_trades[['strategy', 'symbol', 'direction', 'entry_time', 'exit_time', 'pnl', 'exit_reason']].to_markdown() + "\n\n"

    result_md += "### Root Cause Analysis Prompt\n"
    result_md += "Review the trades above. Did the logic fail due to:\n"
    result_md += "1. Gap-up/down?\n"
    result_md += "2. High IV crush?\n"
    result_md += "3. Specific sector meltdown?\n"

    return result_md

def main():
    parser = argparse.ArgumentParser(description='System Audit & Rebalance')
    parser.add_argument('--log-dir', type=str, default=DEFAULT_LOG_DIR, help='Directory containing trade logs')
    args = parser.parse_args()

    print("Loading trades...")
    df = load_trades(args.log_dir)

    if df.empty:
        with open(OUTPUT_FILE, 'w') as f:
            f.write("# System Audit Results\n\nNo trades found to analyze.")
        print("No trades found.")
        return

    print("Analyzing correlation...")
    corr_md, _ = analyze_correlation(df)

    print("Performing stress test...")
    stress_md = stress_test_equity_curve(df)

    final_report = "# System Audit Results\n\n"
    final_report += f"Generated on: {datetime.now()}\n\n"
    final_report += corr_md
    final_report += "\n" + stress_md

    with open(OUTPUT_FILE, 'w') as f:
        f.write(final_report)

    print(f"Audit complete. Results saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
