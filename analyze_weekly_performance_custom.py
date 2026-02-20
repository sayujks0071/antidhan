import os
import glob
import json
import re
from datetime import datetime, timedelta

# Configuration
LOG_DIRS = ["logs"]

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
                if "Signal Buy" in line or "Signal Sell" in line:
                    price_match = re.search(r'Price: ([\d\.]+)', line)
                    if price_match:
                        current_trade = {
                            'strategy': strategy_name,
                            'entry_time': dt,
                            'entry_price': float(price_match.group(1)),
                            'direction': 'LONG' if "Signal Buy" in line else 'SHORT',
                            'status': 'OPEN'
                        }

                # Exit Logic
                if "Exiting" in line and current_trade.get('status') == 'OPEN':
                    price_match = re.search(r'at ([\d\.]+)', line)
                    if price_match:
                        exit_price = float(price_match.group(1))
                        current_trade['exit_time'] = dt
                        current_trade['exit_price'] = exit_price
                        current_trade['status'] = 'CLOSED'
                        if current_trade['direction'] == 'LONG':
                             current_trade['pnl'] = exit_price - current_trade['entry_price']
                        else:
                             current_trade['pnl'] = current_trade['entry_price'] - exit_price

                        trades.append(current_trade)
                        current_trade = {}
    except Exception as e:
        print(f"Error parsing text log {filepath}: {e}")

    return trades

def scan_logs():
    all_trades = []
    print("Scanning logs...")
    for log_dir in LOG_DIRS:
        if not os.path.exists(log_dir):
            continue

        for filepath in glob.glob(os.path.join(log_dir, "*.log")):
            trades = parse_text_log(filepath)
            all_trades.extend(trades)

    return all_trades

def calculate_metrics(trades):
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

        # Net PnL
        net_pnl = sum(t['pnl'] for t in group)

        # Max Drawdown
        group.sort(key=lambda x: x['entry_time'])
        cumulative_pnl = 0
        peak = 0
        drawdowns = []
        current_cum = 0

        for t in group:
            current_cum += t['pnl']
            if current_cum > peak:
                peak = current_cum
            dd = peak - current_cum
            drawdowns.append(dd)

        max_drawdown = max(drawdowns) if drawdowns else 0.0

        metrics[strategy] = {
            'Profit Factor': profit_factor,
            'Max Drawdown': max_drawdown,
            'Win Rate': win_rate,
            'Total Trades': total,
            'Net PnL': net_pnl
        }

    return metrics

def main():
    trades = scan_logs()

    # Filter for last 7 days
    today = datetime.now().date()
    start_date = today - timedelta(days=7)

    week_trades = [t for t in trades if t['entry_time'].date() >= start_date]

    if not week_trades:
        print("No trades found for the past week.")
        return

    metrics = calculate_metrics(week_trades)

    # Sort by Profit Factor desc
    ranked_strategies = sorted(metrics.items(), key=lambda x: x[1]['Profit Factor'], reverse=True)

    print("| Rank | Strategy | Profit Factor | Net PnL | Max Drawdown | Win Rate | Total Trades |")
    print("|------|----------|---------------|---------|--------------|----------|--------------|")

    for rank, (strategy, m) in enumerate(ranked_strategies, 1):
        pf_str = f"{m['Profit Factor']:.2f}" if m['Profit Factor'] != float('inf') else "Inf"
        print(f"| {rank} | {strategy} | {pf_str} | {m['Net PnL']:.2f} | {m['Max Drawdown']:.2f} | {m['Win Rate']:.1f}% | {m['Total Trades']} |")

if __name__ == "__main__":
    main()
