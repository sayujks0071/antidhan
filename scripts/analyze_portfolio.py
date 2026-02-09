import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import glob
import os

LOG_DIRS = [
    "logs",
    "openalgo_backup_20260128_164229/logs"
]

def load_trades():
    all_trades = []

    for log_dir in LOG_DIRS:
        if not os.path.exists(log_dir):
            continue

        json_files = glob.glob(os.path.join(log_dir, "trades_*.json"))

        for filepath in json_files:
            strategy_name = os.path.basename(filepath).replace('trades_', '').replace('.json', '')

            try:
                with open(filepath, 'r') as f:
                    trades = json.load(f)

                for t in trades:
                    # Parse timestamp
                    entry_time = None
                    if 'entry_time' in t:
                        try:
                            entry_time = pd.to_datetime(t['entry_time'])
                        except:
                            pass

                    if entry_time:
                        entry_time = entry_time.replace(tzinfo=None) # naive for simplicity
                        t['entry_time'] = entry_time
                        t['strategy'] = strategy_name
                        all_trades.append(t)

            except Exception as e:
                print(f"Error loading {filepath}: {e}")

    return pd.DataFrame(all_trades)

def analyze_correlation(df):
    if df.empty:
        return pd.DataFrame()

    # Create a time series for each strategy indicating active position (1) or flat (0)
    # Resample to 1 minute

    min_time = df['entry_time'].min().floor('D')
    max_time = df['entry_time'].max().ceil('D')

    # Create index
    idx = pd.date_range(min_time, max_time, freq='1min')

    strategies = df['strategy'].unique()
    signals = pd.DataFrame(index=idx)

    for strat in strategies:
        strat_trades = df[df['strategy'] == strat]
        series = pd.Series(0, index=idx)

        for _, trade in strat_trades.iterrows():
            start = trade['entry_time']
            end = pd.to_datetime(trade.get('exit_time', start + timedelta(hours=1)))
            if pd.isna(end): end = start + timedelta(hours=1)

            # Mark period as 1 (Long) or -1 (Short)
            val = 1 if trade.get('direction', 'LONG') == 'LONG' else -1

            # Handle tz-naive index vs tz-aware trade times if needed
            # Assuming naive for now
            start = start.replace(tzinfo=None)
            end = end.replace(tzinfo=None)

            # using slice to set values
            # Using nearest minute
            start_idx = start.replace(second=0, microsecond=0)
            end_idx = end.replace(second=0, microsecond=0)

            try:
                series.loc[start_idx:end_idx] = val
            except:
                pass

        signals[strat] = series

    # Calculate correlation
    return signals.corr()

def analyze_drawdown(df):
    if df.empty:
        return {}

    metrics = {}
    strategies = df['strategy'].unique()

    for strat in strategies:
        strat_trades = df[df['strategy'] == strat].copy()
        strat_trades = strat_trades.sort_values('entry_time')

        # Cumulative PnL
        strat_trades['cum_pnl'] = strat_trades['pnl'].cumsum()

        # Drawdown
        peak = strat_trades['cum_pnl'].cummax()
        dd = strat_trades['cum_pnl'] - peak
        max_dd = dd.min()

        # Worst Day
        strat_trades['date'] = strat_trades['entry_time'].dt.date
        daily_pnl = strat_trades.groupby('date')['pnl'].sum()
        worst_day = daily_pnl.min()
        worst_day_date = daily_pnl.idxmin()

        # Annualized Return (approximate)
        days = (strat_trades['entry_time'].max() - strat_trades['entry_time'].min()).days
        if days < 1: days = 1
        total_pnl = strat_trades['pnl'].sum()
        annualized_return = (total_pnl / days) * 252 # trading days

        calmar = abs(annualized_return / max_dd) if max_dd != 0 else 0

        metrics[strat] = {
            'Total PnL': total_pnl,
            'Max Drawdown': max_dd,
            'Worst Day PnL': worst_day,
            'Worst Day Date': worst_day_date,
            'Calmar Ratio': calmar
        }

    return metrics

def main():
    print("Loading trades...")
    df = load_trades()

    if df.empty:
        print("No trades found.")
        with open("PORTFOLIO_AUDIT.md", "w") as f:
            f.write("# Portfolio Audit\n\nNo trades found to analyze.")
        return

    print(f"Loaded {len(df)} trades.")

    # Correlation
    print("Calculating correlation...")
    corr_matrix = analyze_correlation(df)

    # Drawdown & Metrics
    print("Calculating metrics...")
    metrics = analyze_drawdown(df)

    # Generate Report
    with open("PORTFOLIO_AUDIT.md", "w") as f:
        f.write("# COMPLETE SYSTEM AUDIT & PORTFOLIO REBALANCING\n\n")

        f.write("## 1. Cross-Strategy Correlation Matrix\n")
        f.write("Correlation of active positions (1min interval):\n\n")
        f.write(corr_matrix.round(2).to_markdown())
        f.write("\n\n")

        # Check for high correlation
        high_corr = []
        visited = set()
        for c1 in corr_matrix.columns:
            for c2 in corr_matrix.columns:
                if c1 != c2 and (c1, c2) not in visited and (c2, c1) not in visited:
                    val = corr_matrix.loc[c1, c2]
                    if abs(val) > 0.7:
                        high_corr.append((c1, c2, val))
                    visited.add((c1, c2))

        if high_corr:
            f.write("**High Correlation Warnings (> 0.7):**\n")
            for c1, c2, val in high_corr:
                f.write(f"- **{c1}** vs **{c2}**: {val:.2f}\n")
                # Recommendation logic
                m1 = metrics.get(c1, {'Calmar Ratio': 0})
                m2 = metrics.get(c2, {'Calmar Ratio': 0})
                better = c1 if m1['Calmar Ratio'] > m2['Calmar Ratio'] else c2
                worse = c2 if better == c1 else c1
                f.write(f"  - Recommendation: Merge into '{better}' (Calmar: {m1['Calmar Ratio']:.2f} vs {m2['Calmar Ratio']:.2f})\n")
        else:
            f.write("No strategies showed high correlation (> 0.7).\n")

        f.write("\n## 2. Strategy Performance & Stress Test\n\n")
        f.write("| Strategy | Total PnL | Max Drawdown | Worst Day PnL | Worst Day Date | Calmar Ratio |\n")
        f.write("|----------|-----------|--------------|---------------|----------------|--------------|\n")

        for strat, m in metrics.items():
            f.write(f"| {strat} | {m['Total PnL']:.2f} | {m['Max Drawdown']:.2f} | {m['Worst Day PnL']:.2f} | {m['Worst Day Date']} | {m['Calmar Ratio']:.2f} |\n")

        f.write("\n## 3. Root Cause Analysis (Worst Day)\n")
        # Find global worst day across all strategies
        global_worst_day_pnl = 0
        global_worst_day_strat = ""
        global_worst_day_date = ""

        for strat, m in metrics.items():
            if m['Worst Day PnL'] < global_worst_day_pnl:
                global_worst_day_pnl = m['Worst Day PnL']
                global_worst_day_strat = strat
                global_worst_day_date = m['Worst Day Date']

        if global_worst_day_strat:
            f.write(f"**Global Worst Day:** {global_worst_day_date} by {global_worst_day_strat} ({global_worst_day_pnl:.2f})\n")
            f.write("- **Analysis**: Verify if this was due to a specific market event (e.g., Gap Down, High VIX).\n")
            f.write("- **Action**: Ensure 'Adaptive Sizing' is enabled to reduce size in high volatility.\n")

    print("PORTFOLIO_AUDIT.md generated.")

if __name__ == "__main__":
    main()
