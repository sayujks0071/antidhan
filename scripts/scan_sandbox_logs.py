import os
import glob
import json
import re
from datetime import datetime, date

# Configuration
LOG_DIRS = [
    "logs",
    "openalgo_backup_20260128_164229/logs"
]

TODAY = datetime.now().date()
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
                    dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue

                # Entry Logic
                if "Buy" in line or "BUY" in line:
                    price_match = re.search(r'Price: ([\d\.]+)', line)
                    if price_match and not current_trade:
                        current_trade = {
                            'entry_time': dt,
                            'entry_price': float(price_match.group(1)),
                            'direction': 'LONG',
                            'status': 'OPEN'
                        }

                # Exit Logic
                if "Trailing Stop Hit" in line or "Exiting" in line or "Stop Loss Hit" in line:
                    if current_trade.get('status') == 'OPEN':
                        price_match = re.search(r'at ([\d\.]+)', line)
                        # Sometimes price might be inferred differently
                        if not price_match:
                             price_match = re.search(r'Price: ([\d\.]+)', line)

                        if price_match:
                            exit_price = float(price_match.group(1))
                            current_trade['exit_time'] = dt
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
                    # Convert timestamps
                    if 'entry_time' in item and isinstance(item['entry_time'], str):
                         try:
                             # Handle ISO format or common formats
                             item['entry_time'] = datetime.fromisoformat(item['entry_time'])
                         except ValueError:
                             try:
                                 item['entry_time'] = datetime.strptime(item['entry_time'], "%Y-%m-%d %H:%M:%S")
                             except:
                                 pass # Keep as string or ignore? Better to ignore if we can't parse date

                    if 'exit_time' in item and isinstance(item['exit_time'], str):
                         try:
                             item['exit_time'] = datetime.fromisoformat(item['exit_time'])
                         except ValueError:
                             try:
                                 item['exit_time'] = datetime.strptime(item['exit_time'], "%Y-%m-%d %H:%M:%S")
                             except:
                                 pass

                    # Ensure PnL
                    if 'pnl' not in item and 'entry_price' in item and 'exit_price' in item:
                        item['pnl'] = float(item['exit_price']) - float(item['entry_price'])

                    # Ensure datetime is present for filtering
                    if 'entry_time' in item and isinstance(item['entry_time'], datetime):
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
            strategy_name = os.path.basename(filepath).split('_')[0]
            for t in trades:
                t['strategy'] = strategy_name
                t['source'] = filepath
            all_trades.extend(trades)

        # JSON logs
        for filepath in glob.glob(os.path.join(log_dir, "trades_*.json")):
            trades = parse_json_log(filepath)
            # Strategy name from filename? trades_StrategyName.json
            filename = os.path.basename(filepath)
            strategy_name = filename.replace('trades_', '').replace('.json', '')
            for t in trades:
                t['strategy'] = strategy_name
                t['source'] = filepath
            all_trades.extend(trades)

    return all_trades

def calculate_metrics(trades):
    # Group by strategy
    strategy_groups = {}
    for t in trades:
        s = t['strategy']
        if s not in strategy_groups:
            strategy_groups[s] = []
        strategy_groups[s].append(t)

    metrics = {}

    for strategy, group in strategy_groups.items():
        # Profit Factor
        gross_profit = sum(t['pnl'] for t in group if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in group if t['pnl'] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss != 0 else float('inf')

        # Win Rate
        wins = len([t for t in group if t['pnl'] > 0])
        total = len(group)
        win_rate = (wins / total) * 100 if total > 0 else 0

        # Max Drawdown
        # Sort by entry time
        group.sort(key=lambda x: x['entry_time'])

        cumulative_pnl = 0
        peak = 0 # assuming starting pnl is 0

        drawdowns = []
        current_cum = 0

        for t in group:
            current_cum += t['pnl']
            if current_cum > peak:
                peak = current_cum
            dd = current_cum - peak
            drawdowns.append(dd)

        max_drawdown = min(drawdowns) if drawdowns else 0.0

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

    # Filter for TODAY
    today_trades = [t for t in trades if t['entry_time'].date() == TODAY]

    markdown_content = f"# SANDBOX LEADERBOARD ({TODAY_STR})\n\n"

    if not today_trades:
        markdown_content += "No trades executed today.\n"
        metrics = {}
    else:
        metrics = calculate_metrics(today_trades)

        # Sort by Profit Factor desc
        ranked_strategies = sorted(metrics.items(), key=lambda x: x[1]['Profit Factor'], reverse=True)

        markdown_content += "| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |\n"
        markdown_content += "|------|----------|---------------|--------------|----------|--------------|\n"

        for rank, (strategy, m) in enumerate(ranked_strategies, 1):
            pf_str = f"{m['Profit Factor']:.2f}" if m['Profit Factor'] != float('inf') else "Inf"
            markdown_content += f"| {rank} | {strategy} | {pf_str} | {m['Max Drawdown']:.2f} | {m['Win Rate']:.1f}% | {m['Total Trades']} |\n"

    markdown_content += "\n## Analysis & Improvements\n"

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
