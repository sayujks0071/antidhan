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

EXPECTED_STRATEGIES = [
    "SuperTrendVWAP",
    "TrendPullback",
    "ORB",
    "AdvancedMLMomentum"
]

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
                    if 'entry_time' in item:
                        try:
                            item['entry_time_dt'] = datetime.fromisoformat(item['entry_time'])
                        except ValueError:
                             pass

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
                if 'entry_time_dt' not in t and 'entry_time' in t:
                     t['entry_time_dt'] = t['entry_time'] # For text logs it is set
            all_trades.extend(trades)

        # JSON logs
        for filepath in glob.glob(os.path.join(log_dir, "trades_*.json")):
            trades = parse_json_log(filepath)
            # Strategy name from filename: trades_ORB.json -> ORB
            strategy_name = os.path.basename(filepath).replace('trades_', '').replace('.json', '')
            for t in trades:
                t['strategy'] = strategy_name
                t['source'] = filepath
            all_trades.extend(trades)

    return all_trades

def calculate_metrics(trades_list):
    grouped = {}
    for t in trades_list:
        s = t.get('strategy', 'Unknown')
        if s not in grouped:
            grouped[s] = []
        grouped[s].append(t)

    metrics = {}

    for strategy, trades in grouped.items():
        gross_profit = 0.0
        gross_loss = 0.0
        wins = 0

        trades.sort(key=lambda x: x.get('entry_time_dt', datetime.min))

        cumulative_pnl = 0.0
        peak = 0.0
        max_drawdown = 0.0

        for t in trades:
            pnl = t.get('pnl', 0.0)
            cumulative_pnl += pnl
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            dd = cumulative_pnl - peak
            if dd < max_drawdown:
                max_drawdown = dd

            if pnl > 0:
                gross_profit += pnl
                wins += 1
            else:
                gross_loss += abs(pnl)

        profit_factor = gross_profit / gross_loss if gross_loss != 0 else float('inf')
        total = len(trades)
        win_rate = (wins / total) * 100 if total > 0 else 0

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

    today_trades = [t for t in trades if t.get('entry_time_dt') and t['entry_time_dt'].date() == TODAY]

    all_metrics = calculate_metrics(trades)

    # Add missing strategies with 0 trades
    for s in EXPECTED_STRATEGIES:
        if s not in all_metrics:
            all_metrics[s] = {
                'Profit Factor': 0.0,
                'Max Drawdown': 0.0,
                'Win Rate': 0.0,
                'Total Trades': 0
            }

    markdown_content = f"# SANDBOX LEADERBOARD ({TODAY_STR})\n\n"

    if not today_trades:
        markdown_content += "No trades executed today.\n"
        markdown_content += "\n## Leaderboard (Based on Latest Available Data)\n"
        today_metrics = all_metrics
    else:
        today_metrics = calculate_metrics(today_trades)
        # Add missing here too if needed, but usually strictly matching today's data.

    # Sort by Profit Factor (desc)
    ranked_strategies = sorted(today_metrics.items(), key=lambda x: x[1]['Profit Factor'], reverse=True)

    markdown_content += "| Rank | Strategy | Profit Factor | Max Drawdown | Win Rate | Total Trades |\n"
    markdown_content += "|------|----------|---------------|--------------|----------|--------------|\n"

    for rank, (strategy, m) in enumerate(ranked_strategies, 1):
        pf_str = f"{m['Profit Factor']:.2f}" if m['Profit Factor'] != float('inf') else "Inf"
        if m['Total Trades'] == 0:
             markdown_content += f"| {rank} | {strategy} | N/A | N/A | N/A | 0 |\n"
        else:
             markdown_content += f"| {rank} | {strategy} | {pf_str} | {m['Max Drawdown']:.2f} | {m['Win Rate']:.1f}% | {m['Total Trades']} |\n"

    markdown_content += "\n## Analysis & Improvements\n"

    for strategy, m in all_metrics.items():
        # Check if trades < 1 (Failed/No Trades) OR Win Rate < 40
        if m['Total Trades'] == 0:
             markdown_content += f"\n### {strategy}\n"
             markdown_content += "- **Status**: No Trades Executed\n"
             markdown_content += "- **Suggestion**: Check data fetching logic (lookback periods), sector data availability, or entry conditions.\n"
        elif m['Win Rate'] < 40:
            markdown_content += f"\n### {strategy}\n"
            markdown_content += f"- **Win Rate**: {m['Win Rate']:.1f}% (< 40%)\n"
            markdown_content += f"- **Profit Factor**: {m['Profit Factor']:.2f}\n"
            markdown_content += "- **Suggestion**: Analyze entry conditions. Check log for rejections or stop loss tightness.\n"

    with open("SANDBOX_LEADERBOARD.md", "w") as f:
        f.write(markdown_content)

    print("SANDBOX_LEADERBOARD.md created.")

    print("\n--- Strategy Analysis ---")
    for strategy, m in all_metrics.items():
        print(f"{strategy}: Win Rate={m['Win Rate']:.1f}%, PF={m['Profit Factor']:.2f}, Trades={m['Total Trades']}")

if __name__ == "__main__":
    main()
