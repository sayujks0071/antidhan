import os
import glob
import re
from datetime import datetime, timedelta

LOG_DIR = "logs"

def parse_log_line(line):
    # Parse timestamp
    match = re.search(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
    if not match:
        return None, None, None

    timestamp_str = match.group(1)
    try:
        dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None, None, None

    if "Signal Buy" in line or "Signal Sell" in line:
        price_match = re.search(r'Price: ([\d\.]+)', line)
        if price_match:
            return dt, 'ENTRY', float(price_match.group(1))

    if "Exiting" in line or "Stop Loss Hit" in line:
        price_match = re.search(r'at ([\d\.]+)', line)
        if price_match:
            return dt, 'EXIT', float(price_match.group(1))

    return None, None, None

def analyze_logs():
    strategies = {}

    # Get all log files in log directory
    log_files = glob.glob(os.path.join(LOG_DIR, "*.log"))

    # Filter for last 7 days (mock data is already last 7 days, but good practice)
    start_date = datetime.now() - timedelta(days=7)

    for filepath in log_files:
        filename = os.path.basename(filepath)
        strategy_name = filename.split('_')[0]

        if strategy_name not in strategies:
            strategies[strategy_name] = {'trades': [], 'pnl': 0.0, 'wins': 0, 'losses': 0}

        current_trade = {}

        with open(filepath, 'r') as f:
            for line in f:
                dt, action, price = parse_log_line(line)
                if not dt:
                    continue

                if dt < start_date:
                    continue

                if action == 'ENTRY':
                    current_trade = {'entry_price': price, 'entry_time': dt}
                elif action == 'EXIT' and current_trade:
                    current_trade['exit_price'] = price
                    current_trade['exit_time'] = dt

                    # Assuming LONG only for mock data simplicity as per generator
                    pnl = price - current_trade['entry_price']

                    strategies[strategy_name]['trades'].append(pnl)
                    strategies[strategy_name]['pnl'] += pnl
                    if pnl > 0:
                        strategies[strategy_name]['wins'] += 1
                    else:
                        strategies[strategy_name]['losses'] += 1

                    current_trade = {}

    # Calculate Metrics
    results = []
    for name, data in strategies.items():
        total_trades = len(data['trades'])
        if total_trades == 0:
            continue

        win_rate = (data['wins'] / total_trades) * 100

        gross_profit = sum(p for p in data['trades'] if p > 0)
        gross_loss = abs(sum(p for p in data['trades'] if p < 0))

        if gross_loss == 0:
            profit_factor = float('inf')
        else:
            profit_factor = gross_profit / gross_loss

        # Max Drawdown
        cumulative = 0
        peak = 0
        drawdown = 0
        for pnl in data['trades']:
            cumulative += pnl
            if cumulative > peak:
                peak = cumulative
            dd = cumulative - peak
            if dd < drawdown:
                drawdown = dd

        results.append({
            'Strategy': name,
            'Net PnL': data['pnl'],
            'Profit Factor': profit_factor,
            'Win Rate': win_rate,
            'Max Drawdown': drawdown,
            'Trades': total_trades
        })

    # Sort by Profit Factor
    results.sort(key=lambda x: x['Profit Factor'], reverse=True)

    # Print Table
    print(f"{'Rank':<5} {'Strategy':<25} {'PF':<10} {'Win Rate':<10} {'Net PnL':<10} {'Max DD':<10}")
    print("-" * 75)
    for i, res in enumerate(results, 1):
        pf_str = f"{res['Profit Factor']:.2f}" if res['Profit Factor'] != float('inf') else "Inf"
        print(f"{i:<5} {res['Strategy']:<25} {pf_str:<10} {res['Win Rate']:.1f}%     {res['Net PnL']:<10.2f} {res['Max Drawdown']:<10.2f}")

    return results

if __name__ == "__main__":
    analyze_logs()
