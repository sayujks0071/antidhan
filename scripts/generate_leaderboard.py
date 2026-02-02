import os
import glob
import json
import re
import pandas as pd
from datetime import datetime

# Configuration
LOG_DIRS = [
    "openalgo/strategies/logs",
    "openalgo/log/strategies",
    "logs",
    "openalgo_backup_20260128_164229/logs"  # Included for reference/fallback
]

TODAY = datetime.now().date()
# Explicitly set today to Feb 1, 2026 as per environment check
# In a real scenario, we would use datetime.now().date(), but for this exercise we want to be precise
# based on the prompt "today".
# However, relying on system date is safer.
TODAY_STR = TODAY.strftime("%Y-%m-%d")

def parse_text_log(filepath):
    trades = []
    current_trade = {}

    with open(filepath, 'r') as f:
        for line in f:
            # Parse timestamp
            # Format: 2026-01-29 10:45:30,123 - Name - INFO - Message
            match = re.search(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if not match:
                continue

            timestamp_str = match.group(1)
            try:
                dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                # Filter for today? Or collect all and filter later?
                # Let's collect all and filter later.
            except ValueError:
                continue

            # Entry Logic (SuperTrend VWAP style)
            # "VWAP Crossover Buy. Price: 123.45, ..."
            if "VWAP Crossover Buy" in line:
                price_match = re.search(r'Price: ([\d\.]+)', line)
                if price_match:
                    current_trade = {
                        'entry_time': dt,
                        'entry_price': float(price_match.group(1)),
                        'direction': 'LONG', # Assumed from "Buy"
                        'status': 'OPEN'
                    }

            # Exit Logic
            # "Trailing Stop Hit at 123.45"
            # "Price crossed below VWAP at 123.45. Exiting."
            if "Trailing Stop Hit at" in line or "Price crossed below VWAP at" in line:
                if current_trade.get('status') == 'OPEN':
                    price_match = re.search(r'at ([\d\.]+)', line)
                    if price_match:
                        exit_price = float(price_match.group(1))
                        current_trade['exit_time'] = dt
                        current_trade['exit_price'] = exit_price
                        current_trade['status'] = 'CLOSED'

                        # Calculate PnL
                        current_trade['pnl'] = (exit_price - current_trade['entry_price'])
                        current_trade['pnl_pct'] = (current_trade['pnl'] / current_trade['entry_price']) * 100

                        trades.append(current_trade)
                        current_trade = {} # Reset

    return trades

def parse_json_log(filepath):
    trades = []
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    # Check if 'entry_time' is present
                    if 'entry_time' in item:
                        # Parse timestamp
                        entry_dt = pd.to_datetime(item['entry_time']).to_pydatetime()
                        item['entry_time'] = entry_dt
                        if 'exit_time' in item:
                             item['exit_time'] = pd.to_datetime(item['exit_time']).to_pydatetime()
                        trades.append(item)
    except Exception as e:
        print(f"Error parsing JSON {filepath}: {e}")
    return trades

def scan_logs():
    all_trades = []

    for log_dir in LOG_DIRS:
        if not os.path.exists(log_dir):
            continue

        print(f"Scanning {log_dir}...")

        # Text logs
        for filepath in glob.glob(os.path.join(log_dir, "*.log")):
            print(f"  Parsing {filepath}...")
            trades = parse_text_log(filepath)
            for t in trades:
                t['strategy'] = os.path.basename(filepath).split('_')[0] # Simple strategy name extraction
                t['source'] = filepath
            all_trades.extend(trades)

        # JSON logs
        for filepath in glob.glob(os.path.join(log_dir, "*.json")):
            # Skip metrics_*.json, only want trades_*.json
            if "trades_" in os.path.basename(filepath):
                print(f"  Parsing {filepath}...")
                trades = parse_json_log(filepath)
                strategy_name = os.path.basename(filepath).replace('trades_', '').replace('.json', '')
                for t in trades:
                    t['strategy'] = strategy_name
                    t['source'] = filepath
                all_trades.extend(trades)

    return all_trades

def calculate_metrics(df):
    metrics = {}

    for strategy, group in df.groupby('strategy'):
        # Profit Factor: Gross Profit / Gross Loss
        gross_profit = group[group['pnl'] > 0]['pnl'].sum()
        gross_loss = abs(group[group['pnl'] < 0]['pnl'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss != 0 else float('inf')

        # Win Rate
        wins = len(group[group['pnl'] > 0])
        total = len(group)
        win_rate = (wins / total) * 100 if total > 0 else 0

        # Max Drawdown (simplified using cumsum of pnl)
        group = group.sort_values('entry_time')
        cumulative_pnl = group['pnl'].cumsum()
        peak = cumulative_pnl.expanding(min_periods=1).max()
        drawdown = cumulative_pnl - peak
        max_drawdown = drawdown.min()

        metrics[strategy] = {
            'Profit Factor': profit_factor,
            'Max Drawdown': max_drawdown,
            'Win Rate': win_rate,
            'Total Trades': total
        }

    return metrics

def main():
    print(f"Generating Sandbox Leaderboard for {TODAY_STR}")
    trades = scan_logs()

    if not trades:
        print("No trades found in any log files.")
        # Proceed to generate empty leaderboard
        df = pd.DataFrame(columns=['strategy', 'pnl', 'entry_time'])
    else:
        df = pd.DataFrame(trades)

        # Filter for TODAY
        # Adjust logic: parse string timestamps if necessary
        # The parsers return datetime objects

        # For this exercise, we strictly filter for TODAY.
        # But if no trades today, we might want to show message.
        today_trades = df[df['entry_time'].apply(lambda x: x.date() == TODAY)]

        print(f"Found {len(df)} total trades. {len(today_trades)} trades from today ({TODAY_STR}).")

        if today_trades.empty:
             print("No trades found for today. Using all trades for demonstration (optional) or reporting empty.")
             # Based on prompt "Extract ... for every trade executed ... today"
             # If empty, we stick to empty.
             df = pd.DataFrame(columns=['strategy', 'pnl', 'entry_time'])
        else:
             df = today_trades

    if df.empty:
        markdown_content = f"# SANDBOX LEADERBOARD ({TODAY_STR})\n\nNo trades executed today.\n"
    else:
        metrics = calculate_metrics(df)

        # Rank by Profit Factor (desc) and Max Drawdown (desc/closest to 0)
        # We'll just sort by Profit Factor for now as primary
        ranked_strategies = sorted(metrics.items(), key=lambda x: x[1]['Profit Factor'], reverse=True)

        markdown_content = f"# SANDBOX LEADERBOARD ({TODAY_STR})\n\n"
        markdown_content += "| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |\n"
        markdown_content += "|------|----------|---------------|--------------|----------|--------------|\n"

        for rank, (strategy, m) in enumerate(ranked_strategies, 1):
            pf_str = f"{m['Profit Factor']:.2f}" if m['Profit Factor'] != float('inf') else "Inf"
            markdown_content += f"| {rank} | {strategy} | {pf_str} | {m['Max Drawdown']:.2f} | {m['Win Rate']:.1f}% | {m['Total Trades']} |\n"

        markdown_content += "\n## Improvement Suggestions\n"
        for strategy, m in metrics.items():
            if m['Win Rate'] < 40:
                markdown_content += f"\n### {strategy}\n"
                markdown_content += f"- **Win Rate**: {m['Win Rate']:.1f}% (< 40%)\n"
                markdown_content += "- **Suggestion**: Analyze entry conditions. Check log for rejections or stop loss tightness.\n"

    with open("SANDBOX_LEADERBOARD.md", "w") as f:
        f.write(markdown_content)

    print("SANDBOX_LEADERBOARD.md created.")

if __name__ == "__main__":
    main()
