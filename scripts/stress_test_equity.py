import os
import json
import pandas as pd
import glob
from datetime import datetime

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
                    if isinstance(t.get('exit_time'), str):
                        try:
                            t['exit_time'] = pd.to_datetime(t['exit_time'])
                        except:
                            continue

                    # Ensure PnL
                    if 'pnl' not in t:
                        if 'entry_price' in t and 'exit_price' in t:
                            qty = t.get('quantity', 1)
                            direction = 1 if t.get('direction', 'LONG') == 'LONG' else -1
                            t['pnl'] = (t['exit_price'] - t['entry_price']) * qty * direction
                        else:
                            t['pnl'] = 0.0

                    all_trades.append(t)
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
    return all_trades

def generate_report():
    trades = load_trades()
    if not trades:
        print("No trades found.")
        return

    df_trades = pd.DataFrame(trades)
    if df_trades.empty:
        print("No valid trades found.")
        return

    # Calculate Daily PnL
    df_trades['date'] = df_trades['exit_time'].dt.date
    daily_pnl = df_trades.groupby('date')['pnl'].sum().sort_index()

    # Calculate Monthly PnL
    df_trades['month'] = df_trades['exit_time'].dt.to_period('M')
    monthly_pnl = df_trades.groupby('month')['pnl'].sum().sort_index()

    # Identify Worst Day
    if daily_pnl.empty:
        worst_day = None
        worst_pnl = 0
    else:
        worst_day = daily_pnl.idxmin()
        worst_pnl = daily_pnl.min()

    # Generate Report
    with open("EQUITY_CURVE_REPORT.md", "w") as f:
        f.write("# Equity Curve Stress Test Report\n\n")

        f.write("## Monthly Performance\n")
        f.write("| Month | PnL |\n|---|---|\n")
        for m, pnl in monthly_pnl.items():
            f.write(f"| {m} | {pnl:.2f} |\n")

        f.write("\n## Daily Performance (Last 10 Days)\n")
        f.write("| Date | PnL |\n|---|---|\n")
        for d, pnl in daily_pnl.tail(10).items():
            f.write(f"| {d} | {pnl:.2f} |\n")

        f.write(f"\n## Worst Day Analysis\n")
        if worst_day:
            f.write(f"- **Date**: {worst_day}\n")
            f.write(f"- **PnL**: {worst_pnl:.2f}\n")

            # Detailed trades for that day
            daily_trades = df_trades[df_trades['date'] == worst_day]
            f.write("\n### Trades on Worst Day\n")
            f.write(daily_trades[['strategy', 'entry_time', 'exit_time', 'direction', 'pnl']].to_markdown(index=False))

            # Root Cause Analysis (Simulated based on worst performing strategy)
            worst_strat = daily_trades.groupby('strategy')['pnl'].sum().idxmin()
            worst_strat_pnl = daily_trades.groupby('strategy')['pnl'].sum().min()

            f.write(f"\n\n### Root Cause Analysis (Simulated)\n")
            f.write(f"- **Primary Contributor**: {worst_strat} ({worst_strat_pnl:.2f})\n")
            f.write("- **Potential Causes**:\n")
            f.write("  1. **Gap Handling**: Did the market gap against the position?\n")
            f.write("  2. **High Volatility**: Was IV exceptionally high, causing stop loss hit on wide moves?\n")
            f.write("  3. **Sector Correlation**: Did the sector drag the stock down despite technical setup?\n")

            f.write("\n### Recommended Action\n")
            f.write(f"- Review {worst_strat} logic for gap detection.\n")
            f.write("- Consider adding VIX-based volatility filter (skip if VIX > 25).\n")
            f.write("- Verify if sector filter was active.\n")

        else:
            f.write("No daily PnL data available.\n")

    print("EQUITY_CURVE_REPORT.md generated.")

if __name__ == "__main__":
    generate_report()
