import os
import json
import pandas as pd
import glob
from datetime import datetime, timedelta

LOG_DIR = "openalgo_backup_20260128_164229/logs"

def load_trades():
    all_trades = []
    if not os.path.exists(LOG_DIR):
        print(f"Log directory {LOG_DIR} not found.")
        return []

    files = glob.glob(os.path.join(LOG_DIR, "trades_*.json"))
    for filepath in files:
        strategy_name = os.path.basename(filepath).replace('trades_', '').replace('.json', '')
        try:
            with open(filepath, 'r') as f:
                trades = json.load(f)
                for t in trades:
                    t['strategy'] = strategy_name
                    # Parse dates
                    if isinstance(t.get('entry_time'), str):
                        try:
                            t['entry_time'] = pd.to_datetime(t['entry_time'])
                        except:
                            continue
                    if isinstance(t.get('exit_time'), str):
                        try:
                            t['exit_time'] = pd.to_datetime(t['exit_time'])
                        except:
                            continue
                    all_trades.append(t)
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
    return all_trades

def analyze_correlation():
    trades = load_trades()
    if not trades:
        print("No trades found.")
        return

    df_trades = pd.DataFrame(trades)
    if df_trades.empty:
        print("No valid trades found.")
        return

    # Determine time range
    min_time = df_trades['entry_time'].min()
    max_time = df_trades['exit_time'].max()

    if pd.isna(min_time) or pd.isna(max_time):
        print("Invalid time range.")
        return

    # Create hourly index
    full_range = pd.date_range(start=min_time.floor('h'), end=max_time.ceil('h'), freq='h')
    positions = pd.DataFrame(index=full_range)

    strategies = df_trades['strategy'].unique()

    for strategy in strategies:
        strat_trades = df_trades[df_trades['strategy'] == strategy]
        pos_series = pd.Series(0, index=full_range)

        for index, trade in strat_trades.iterrows():
            entry = trade['entry_time']
            exit = trade['exit_time']
            direction = 1 if trade.get('direction', 'LONG') == 'LONG' else -1

            # Mark position for the duration
            # Identify hours within [entry, exit]
            mask = (full_range >= entry) & (full_range <= exit)
            pos_series[mask] = direction

        positions[strategy] = pos_series

    # Calculate correlation
    corr_matrix = positions.corr()
    print("Correlation Matrix:")
    print(corr_matrix)

    # Save to file
    with open("CORRELATION_ANALYSIS.md", "w") as f:
        f.write("# Cross-Strategy Correlation Analysis\n\n")
        f.write("## Correlation Matrix\n\n")
        f.write(corr_matrix.to_markdown())
        f.write("\n\n## Analysis\n")

        high_corr_pairs = []
        for i in range(len(corr_matrix.columns)):
            for j in range(i+1, len(corr_matrix.columns)):
                val = corr_matrix.iloc[i, j]
                s1 = corr_matrix.columns[i]
                s2 = corr_matrix.columns[j]
                if abs(val) > 0.7:
                    high_corr_pairs.append((s1, s2, val))
                    f.write(f"- **High Correlation ({val:.2f})**: {s1} vs {s2}\n")

        if not high_corr_pairs:
            f.write("- No strategies found with > 0.7 correlation.\n")
        else:
            f.write("\n## Recommendations\n")
            for s1, s2, val in high_corr_pairs:
                f.write(f"- Consider merging **{s1}** and **{s2}** or disabling one.\n")

if __name__ == "__main__":
    analyze_correlation()
