import os
import glob
import json
import re
import datetime

# Configuration
LOG_DIRS = [
    "logs",
    "openalgo_backup_20260128_164229/logs"
]

TODAY = datetime.date.today()
TODAY_STR = TODAY.strftime("%Y-%m-%d")

def parse_text_log(filepath):
    trades = []
    current_trade = {}

    try:
        with open(filepath, 'r') as f:
            for line in f:
                # Parse timestamp
                match = re.search(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if not match:
                    continue

                timestamp_str = match.group(1)
                try:
                    dt = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue

                # Entry Logic
                if "Buy" in line or "BUY" in line:
                    price_match = re.search(r'Price: ([\d\.]+)', line)
                    if price_match and not current_trade:
                        current_trade = {
                            'entry_time_dt': dt,
                            'entry_date': dt.date(),
                            'entry_price': float(price_match.group(1)),
                            'direction': 'LONG',
                            'status': 'OPEN',
                            'pnl': 0.0
                        }

                # Exit Logic
                if "Trailing Stop Hit" in line or "Exiting" in line or "Stop Loss Hit" in line:
                    if current_trade.get('status') == 'OPEN':
                        price_match = re.search(r'at ([\d\.]+)', line)
                        if not price_match:
                             price_match = re.search(r'Price: ([\d\.]+)', line)

                        if price_match:
                            exit_price = float(price_match.group(1))
                            current_trade['exit_time_dt'] = dt
                            current_trade['exit_price'] = exit_price
                            current_trade['status'] = 'CLOSED'
                            current_trade['pnl'] = (exit_price - current_trade['entry_price'])
                            trades.append(current_trade)
                            current_trade = {}
    except Exception as e:
        print(f"Error parsing text log {filepath}: {e}")

    return trades

def parse_json_log(filepath):
    trades = []
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    # Normalize keys
                    if 'entry_time' in item:
                        # Parse timestamp
                        try:
                            entry_dt = datetime.datetime.fromisoformat(item['entry_time'])
                        except ValueError:
                            try:
                                entry_dt = datetime.datetime.strptime(item['entry_time'], "%Y-%m-%d %H:%M:%S")
                            except ValueError:
                                # Fallback or skip
                                continue

                        item['entry_time_dt'] = entry_dt
                        item['entry_date'] = entry_dt.date()

                        if 'exit_time' in item and item['exit_time']:
                            try:
                                exit_dt = datetime.datetime.fromisoformat(item['exit_time'])
                                item['exit_time_dt'] = exit_dt
                            except ValueError:
                                pass

                        # Ensure numeric
                        item['pnl'] = float(item.get('pnl', 0.0))
                        item['entry_price'] = float(item.get('entry_price', 0.0))
                        item['exit_price'] = float(item.get('exit_price', 0.0))

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
            trades = parse_text_log(filepath)
            for t in trades:
                t['strategy'] = os.path.basename(filepath).split('_')[0]
                t['source'] = filepath
            all_trades.extend(trades)

        # JSON logs
        for filepath in glob.glob(os.path.join(log_dir, "trades_*.json")):
            trades = parse_json_log(filepath)
            strategy_name = os.path.basename(filepath).replace('trades_', '').replace('.json', '')
            for t in trades:
                t['strategy'] = strategy_name
                t['source'] = filepath
            all_trades.extend(trades)

    return all_trades

def calculate_metrics(trades):
    metrics = {}

    # Group by strategy
    strategies = {}
    for t in trades:
        s = t.get('strategy', 'Unknown')
        if s not in strategies:
            strategies[s] = []
        strategies[s].append(t)

    for strategy, group in strategies.items():
        # Sort by entry time
        group.sort(key=lambda x: x.get('entry_time_dt', datetime.datetime.min))

        # Profit Factor
        gross_profit = sum(t['pnl'] for t in group if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in group if t['pnl'] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss != 0 else float('inf')

        # Win Rate
        wins = len([t for t in group if t['pnl'] > 0])
        total = len(group)
        win_rate = (wins / total) * 100 if total > 0 else 0

        # Max Drawdown
        cumulative_pnl = 0
        peak = 0
        max_drawdown = 0

        for t in group:
            cumulative_pnl += t['pnl']
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            drawdown = cumulative_pnl - peak
            if drawdown < max_drawdown:
                max_drawdown = drawdown

        metrics[strategy] = {
            'Profit Factor': profit_factor,
            'Max Drawdown': max_drawdown,
            'Win Rate': win_rate,
            'Total Trades': total
        }

    return metrics

def main():
    print(f"Generating Sandbox Leaderboard for {TODAY_STR}")
    all_trades = scan_logs()

    # Filter for TODAY
    today_trades = [t for t in all_trades if t.get('entry_date') == TODAY]

    markdown_content = f"# SANDBOX LEADERBOARD ({TODAY_STR})\n\n"

    if not today_trades:
        print("No trades found for today.")
        markdown_content += "No trades executed today.\n"

        # Fallback to historical for improvement analysis
        print("Analyzing historical trades for improvement suggestions...")
        historical_metrics = calculate_metrics(all_trades)
        display_metrics = {}
        analysis_metrics = historical_metrics
        if historical_metrics:
            markdown_content += "\n> **Note:** Leaderboard is empty due to no trades today. Improvement suggestions below are based on historical data.\n"
    else:
        print(f"Found {len(today_trades)} trades for today.")
        display_metrics = calculate_metrics(today_trades)
        analysis_metrics = display_metrics

    # Leaderboard Section
    if display_metrics:
        # Sort by Profit Factor desc
        ranked_strategies = sorted(display_metrics.items(), key=lambda x: x[1]['Profit Factor'], reverse=True)

        markdown_content += "| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |\n"
        markdown_content += "|------|----------|---------------|--------------|----------|--------------|\n"

        for rank, (strategy, m) in enumerate(ranked_strategies, 1):
            pf_str = f"{m['Profit Factor']:.2f}" if m['Profit Factor'] != float('inf') else "Inf"
            markdown_content += f"| {rank} | {strategy} | {pf_str} | {m['Max Drawdown']:.2f} | {m['Win Rate']:.1f}% | {m['Total Trades']} |\n"

    # Improvement Section
    markdown_content += "\n## Analysis & Improvements\n"

    improvement_needed = False
    for strategy, m in analysis_metrics.items():
        if m['Win Rate'] < 40:
            improvement_needed = True
            markdown_content += f"\n### {strategy}\n"
            markdown_content += f"- **Win Rate**: {m['Win Rate']:.1f}% (< 40%)\n"
            markdown_content += f"- **Profit Factor**: {m['Profit Factor']:.2f}\n"
            markdown_content += "- **Suggestion**: Strategy has a low win rate. Investigate entry logic to reduce false positives. Consider adding trend filters (e.g., ADX > 25) or tightening stop losses.\n"
            print(f"Strategy {strategy} needs improvement (Win Rate: {m['Win Rate']:.1f}%)")

    if not improvement_needed and analysis_metrics:
        markdown_content += "\nAll strategies (historical or current) have Win Rate >= 40%. No immediate improvements required based on this metric.\n"
        print("No strategies found with Win Rate < 40%.")
    elif not analysis_metrics:
        markdown_content += "\nNo trade data available for analysis.\n"

    with open("SANDBOX_LEADERBOARD.md", "w") as f:
        f.write(markdown_content)

    print("SANDBOX_LEADERBOARD.md created.")

if __name__ == "__main__":
    main()
