import os
import glob
import json
import re
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Configuration
LOG_DIRS = [
    "logs",
    "openalgo_backup_*/logs",
    "openalgo/log/strategies"  # Added based on previous exploration finding openalgo/log
]

def parse_text_log(filepath):
    trades = []
    current_trade = {}
    strategy_name = os.path.basename(filepath).split('_')[0]

    try:
        with open(filepath, 'r') as f:
            for line in f:
                # Parse timestamp
                match = re.search(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if not match:
                    continue

                timestamp_str = match.group(1)
                try:
                    dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue

                # Entry Logic
                if "Buy" in line or "BUY" in line or "Short" in line or "SHORT" in line:
                    if "Entry" in line or "Executing" in line:
                         price_match = re.search(r'Price: ([\d\.]+)', line)
                         # Also try to find symbol
                         symbol_match = re.search(r'Executing \w+ \d+ (\w+)', line)
                         symbol = symbol_match.group(1) if symbol_match else "Unknown"

                         if price_match:
                            current_trade = {
                                'entry_time': dt,
                                'entry_price': float(price_match.group(1)),
                                'direction': 'LONG' if 'Buy' in line or 'BUY' in line else 'SHORT',
                                'status': 'OPEN',
                                'symbol': symbol,
                                'strategy': strategy_name
                            }

                # Exit Logic
                if "Trailing Stop Hit" in line or "Exiting" in line or "Stop Loss Hit" in line:
                    if current_trade.get('status') == 'OPEN':
                        price_match = re.search(r'at ([\d\.]+)', line)
                        if not price_match:
                             price_match = re.search(r'Price: ([\d\.]+)', line)

                        if price_match:
                            exit_price = float(price_match.group(1))
                            current_trade['exit_time'] = dt
                            current_trade['exit_price'] = exit_price
                            current_trade['status'] = 'CLOSED'

                            qty = 1 # Default
                            # Try to extract quantity
                            qty_match = re.search(r'Qty: (\d+)', line)
                            if qty_match:
                                qty = int(qty_match.group(1))

                            pnl = (exit_price - current_trade['entry_price']) * qty if current_trade['direction'] == 'LONG' else (current_trade['entry_price'] - exit_price) * qty
                            current_trade['pnl'] = pnl
                            trades.append(current_trade)
                            current_trade = {}
    except Exception as e:
        print(f"Error parsing text log {filepath}: {e}")

    return trades

def parse_json_log(filepath):
    trades = []
    strategy_name = os.path.basename(filepath).replace('trades_', '').replace('.json', '')
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    item['strategy'] = strategy_name
                    # Ensure timestamps are datetime
                    if 'entry_time' in item and isinstance(item['entry_time'], str):
                        item['entry_time'] = pd.to_datetime(item['entry_time'])
                    if 'exit_time' in item and isinstance(item['exit_time'], str):
                        item['exit_time'] = pd.to_datetime(item['exit_time'])

                    if 'pnl' not in item and 'entry_price' in item and 'exit_price' in item:
                         direction = item.get('direction', 'LONG')
                         qty = item.get('quantity', 1)
                         if direction == 'LONG':
                             item['pnl'] = (item['exit_price'] - item['entry_price']) * qty
                         else:
                             item['pnl'] = (item['entry_price'] - item['exit_price']) * qty

                    trades.append(item)
    except Exception as e:
        print(f"Error parsing JSON {filepath}: {e}")
    return trades

def scan_logs():
    all_trades = []

    # Expand globs for backup dirs
    expanded_dirs = []
    for d in LOG_DIRS:
        expanded_dirs.extend(glob.glob(d))

    unique_dirs = set(expanded_dirs)

    for log_dir in unique_dirs:
        if not os.path.exists(log_dir):
            continue

        print(f"Scanning {log_dir}...")

        # Text logs
        for filepath in glob.glob(os.path.join(log_dir, "*.log")):
            trades = parse_text_log(filepath)
            all_trades.extend(trades)

        # JSON logs
        for filepath in glob.glob(os.path.join(log_dir, "trades_*.json")):
            trades = parse_json_log(filepath)
            all_trades.extend(trades)

    return all_trades

def analyze_system():
    trades = scan_logs()
    if not trades:
        print("No trades found.")
        with open("audit_results.md", "w") as f:
            f.write("# System Audit Report\n\nNo trades found in logs.")
        return

    df = pd.DataFrame(trades)
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    df['date'] = df['entry_time'].dt.date

    # 1. Equity Curve & Worst Day
    daily_pnl = df.groupby('date')['pnl'].sum().sort_index()
    if daily_pnl.empty:
         worst_day_str = "N/A"
         worst_day_pnl = 0
    else:
        worst_day = daily_pnl.idxmin()
        worst_day_pnl = daily_pnl.min()
        worst_day_str = str(worst_day)

    # Strategies on worst day
    worst_day_strategies = []
    if worst_day_str != "N/A":
        worst_day_trades = df[df['date'] == worst_day]
        worst_day_strategies = worst_day_trades.groupby('strategy')['pnl'].sum().sort_values().to_dict()

    # 2. Correlation Analysis
    # Create a time series for each strategy: 1 if active (entry) in an hour, 0 otherwise
    # Resample to 1H
    df['hour'] = df['entry_time'].dt.floor('h')
    pivot = df.pivot_table(index='hour', columns='strategy', values='pnl', aggfunc='count').fillna(0)
    # Convert to binary (active or not)
    binary_activity = (pivot > 0).astype(int)

    correlation_matrix = binary_activity.corr()

    # Generate Report
    with open("audit_results.md", "w") as f:
        f.write("# System Audit & Portfolio Rebalancing Report\n\n")

        f.write("## 1. Equity Curve Stress Test\n")
        f.write(f"- **Worst Day**: {worst_day_str}\n")
        f.write(f"- **Net PnL on Worst Day**: {worst_day_pnl:.2f}\n")
        if worst_day_strategies:
            f.write("### Strategy Breakdown (Worst Day):\n")
            f.write("| Strategy | PnL |\n|---|---|\n")
            for strat, pnl in worst_day_strategies.items():
                f.write(f"| {strat} | {pnl:.2f} |\n")

        f.write("\n## 2. Cross-Strategy Correlation\n")
        f.write("Correlation based on hourly entry activity:\n\n")

        # Write matrix as table
        if not correlation_matrix.empty:
            f.write(correlation_matrix.to_markdown())
            f.write("\n\n### High Correlation Pairs (> 0.7)\n")

            high_corr_pairs = []
            cols = correlation_matrix.columns
            for i in range(len(cols)):
                for j in range(i+1, len(cols)):
                    val = correlation_matrix.iloc[i, j]
                    if val > 0.7:
                        f.write(f"- **{cols[i]}** vs **{cols[j]}**: {val:.2f}\n")
                        high_corr_pairs.append((cols[i], cols[j], val))

            if not high_corr_pairs:
                f.write("No high correlation pairs found.\n")
        else:
            f.write("Insufficient data for correlation analysis.\n")

    print("Audit completed. Results in audit_results.md")

if __name__ == "__main__":
    try:
        analyze_system()
    except Exception as e:
        print(f"Audit failed: {e}")
        import traceback
        traceback.print_exc()
