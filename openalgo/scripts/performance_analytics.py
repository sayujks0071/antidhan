#!/usr/bin/env python3
"""
Daily Performance Analytics & Attribution
-----------------------------------------
Analyzes strategy logs to provide deep insights into trading performance:
- Win Rate, Profit Factor, Risk:Reward
- Trade Duration Analysis
- Time of Day Attribution
- Strategy Comparison
"""

import os
import sys
import re
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

try:
    import tabulate
except ImportError:
    tabulate = None

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(repo_root)

# Paths
LOG_DIR = os.path.join(repo_root, 'openalgo/strategies/logs')
ALT_LOG_DIR = os.path.join(repo_root, 'openalgo/log/strategies')

class PerformanceAnalyzer:
    def __init__(self, lookback_days=30):
        self.lookback_days = lookback_days
        self.trades = []

    def find_logs(self):
        logs = []
        for d in [LOG_DIR, ALT_LOG_DIR]:
            if os.path.exists(d):
                logs.extend([os.path.join(d, f) for f in os.listdir(d) if f.endswith('.log')])
        return logs

    def parse_logs(self):
        log_files = self.find_logs()
        print(f"Scanning {len(log_files)} log files...")

        # Regex patterns
        time_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')
        pnl_pattern = re.compile(r'PnL[:=]\s*([-\d.]+)', re.I)
        pos_pattern = re.compile(r'Position Updated.*:\s*([-\d]+)\s*@', re.I)

        for log_file in log_files:
            strategy_name = os.path.basename(log_file).replace('.log', '')
            strategy_name = re.sub(r'_\d{8}.*', '', strategy_name)

            # State for this file
            entry_time = None

            with open(log_file, 'r', errors='ignore') as f:
                for line in f:
                    time_match = time_pattern.search(line)
                    if not time_match:
                        continue

                    timestamp_str = time_match.group(1)
                    try:
                        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        continue

                    if (datetime.now() - timestamp).days > self.lookback_days:
                        continue

                    # Track Entry / Position State
                    if "Position Updated" in line:
                        pos_match = pos_pattern.search(line)
                        if pos_match:
                            try:
                                pos = int(pos_match.group(1))
                                if pos != 0:
                                    # Entry (only if we don't have one, assuming FIFO/single position)
                                    if entry_time is None:
                                        entry_time = timestamp
                                else:
                                    # Position closed
                                    entry_time = None
                            except ValueError:
                                pass

                    # Track Exit / PnL
                    if 'pnl' in line.lower() and ('closed' in line.lower() or 'exit' in line.lower()):
                        pnl_match = pnl_pattern.search(line)
                        if pnl_match:
                            try:
                                pnl = float(pnl_match.group(1))

                                duration_mins = 0
                                if entry_time:
                                    duration = timestamp - entry_time
                                    duration_mins = duration.total_seconds() / 60

                                self.trades.append({
                                    'strategy': strategy_name,
                                    'exit_time': timestamp,
                                    'entry_time': entry_time,
                                    'duration_mins': duration_mins,
                                    'pnl': pnl,
                                    'hour': timestamp.hour
                                })
                            except ValueError:
                                pass

    def generate_report(self):
        if not self.trades:
            print("No trades found in the last {} days.".format(self.lookback_days))
            return

        df = pd.DataFrame(self.trades)

        print("\n" + "="*60)
        print(f"📊 PERFORMANCE REPORT (Last {self.lookback_days} Days)")
        print("="*60)

        # 1. Overall Metrics
        total_pnl = df['pnl'].sum()
        total_trades = len(df)
        wins = df[df['pnl'] > 0]
        losses = df[df['pnl'] <= 0]

        win_rate = len(wins) / total_trades * 100
        gross_profit = wins['pnl'].sum()
        gross_loss = abs(losses['pnl'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        avg_win = wins['pnl'].mean() if not wins.empty else 0
        avg_loss = losses['pnl'].mean() if not losses.empty else 0
        avg_duration = df['duration_mins'].mean()

        print(f"\n📈 OVERALL SUMMARY")
        print(f"Total P&L:       ₹{total_pnl:,.2f}")
        print(f"Total Trades:    {total_trades}")
        print(f"Win Rate:        {win_rate:.1f}%")
        print(f"Profit Factor:   {profit_factor:.2f}")
        print(f"Avg Win:         ₹{avg_win:,.2f}")
        print(f"Avg Loss:        ₹{avg_loss:,.2f}")
        print(f"Avg Duration:    {avg_duration:.1f} mins")

        # Helper for printing tables
        def print_table(df_table, headers):
            if tabulate:
                print(tabulate.tabulate(df_table, headers=headers, tablefmt="github", floatfmt=".2f"))
            else:
                print(df_table.to_string())

        # 2. Strategy Breakdown
        print(f"\n🏆 STRATEGY PERFORMANCE")
        strat_group = df.groupby('strategy').agg({
            'pnl': ['sum', 'count', 'mean'],
            'duration_mins': 'mean'
        })
        strat_group['win_rate'] = df.groupby('strategy')['pnl'].apply(lambda x: (x > 0).mean() * 100)

        # Flatten columns
        strat_group.columns = ['Total P&L', 'Trades', 'Avg P&L', 'Avg Dur (m)', 'Win Rate %']
        strat_group = strat_group.sort_values('Total P&L', ascending=False)

        print_table(strat_group, headers="keys")

        # 3. Time of Day Attribution
        print(f"\n⏰ P&L BY HOUR OF DAY")
        hourly = df.groupby('hour')['pnl'].agg(['sum', 'count', 'mean']).sort_index()
        hourly.columns = ['Total P&L', 'Trades', 'Avg P&L']
        print_table(hourly, headers="keys")

        # 4. Best Hour vs Worst Hour
        if not hourly.empty:
            best_hour = hourly['Total P&L'].idxmax()
            worst_hour = hourly['Total P&L'].idxmin()
            print(f"\n✅ Best Performing Hour: {best_hour}:00 - {best_hour+1}:00")
            print(f"❌ Worst Performing Hour: {worst_hour}:00 - {worst_hour+1}:00")

def main():
    parser = argparse.ArgumentParser(description="Performance Analytics")
    parser.add_argument("--days", type=int, default=30, help="Lookback days")
    args = parser.parse_args()

    analyzer = PerformanceAnalyzer(lookback_days=args.days)
    analyzer.parse_logs()
    analyzer.generate_report()

if __name__ == "__main__":
    main()
