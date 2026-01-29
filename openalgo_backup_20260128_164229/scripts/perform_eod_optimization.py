import os
import re
import glob
import csv
from datetime import datetime
from collections import defaultdict
import json

# Configuration
LOG_DIRS = ["openalgo/strategies/logs", "openalgo/log/strategies"]
STRATEGIES_DIR = "openalgo/strategies/scripts"
RANKINGS_DIR = "openalgo/strategies/backtest_results"
DEPLOY_SCRIPT_PATH = "openalgo/strategies/scripts/deploy_daily_optimized.sh"

def get_today_logs():
    """Finds log files for the current date across multiple directories."""
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    log_files = []

    # Also support yyyy-mm-dd format in filename if present
    date_str_dash = now.strftime("%Y-%m-%d")

    for log_dir in LOG_DIRS:
        if not os.path.exists(log_dir):
            continue

        # Look for *20240128* or *2024-01-28*
        patterns = [
            os.path.join(log_dir, f"*{date_str}*.log"),
            os.path.join(log_dir, f"*{date_str_dash}*.log")
        ]

        for pattern in patterns:
            found = glob.glob(pattern)
            log_files.extend(found)

    return list(set(log_files))

def parse_log_file(filepath):
    """Parses a single log file and returns metrics."""
    metrics = {
        "signals": 0,
        "entries": 0,
        "exits": 0,
        "rejected": 0,
        "errors": 0,
        "pnl": 0.0,
        "wins": 0,
        "losses": 0,
        "total_win_pnl": 0.0,
        "total_loss_pnl": 0.0,
        "rejected_reasons": defaultdict(int),
        "rejected_scores": []
    }

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            # Metrics line
            metrics_match = re.search(r'\[METRICS\]\s+signals=(\d+)\s+entries=(\d+)\s+exits=(\d+)\s+rejected=(\d+)\s+errors=(\d+)\s+pnl=([\d.-]+)', line, re.I)
            if metrics_match:
                metrics['signals'] = max(metrics['signals'], int(metrics_match.group(1)))
                metrics['entries'] = max(metrics['entries'], int(metrics_match.group(2)))
                metrics['exits'] = max(metrics['exits'], int(metrics_match.group(3)))
                metrics['rejected'] = max(metrics['rejected'], int(metrics_match.group(4)))
                metrics['errors'] = max(metrics['errors'], int(metrics_match.group(5)))
                metrics['pnl'] = max(metrics['pnl'], float(metrics_match.group(6)))

            # Rejected Signal
            rejected_match = re.search(r'\[REJECTED\]\s+symbol=(\S+)\s+score=([\d.]+)\s+reason=(.+)', line, re.I)
            if rejected_match:
                metrics['rejected_reasons'][rejected_match.group(3).strip()] += 1
                try:
                    metrics['rejected_scores'].append(float(rejected_match.group(2)))
                except ValueError:
                    pass

            # Exit / PnL
            # Matches: [EXIT] symbol=... pnl=100.0 or PnL: 100.0
            exit_pnl_match = re.search(r'pnl=([\d.-]+)', line, re.I)
            if not exit_pnl_match:
                exit_pnl_match = re.search(r'PnL:\s+([\d.-]+)', line, re.I)

            if exit_pnl_match and ('[EXIT]' in line or 'Exiting' in line or 'Closed' in line):
                try:
                    pnl = float(exit_pnl_match.group(1))
                    if pnl > 0:
                        metrics['wins'] += 1
                        metrics['total_win_pnl'] += pnl
                    elif pnl < 0:
                        metrics['losses'] += 1
                        metrics['total_loss_pnl'] += abs(pnl)
                except ValueError:
                    pass

            # Errors
            if '[ERROR]' in line or 'ERROR' in line:
                metrics['errors'] += 1

    return metrics

def analyze_strategy(strategy_name, log_files):
    """Aggregates metrics for a strategy across multiple log files."""
    aggregated = {
        "signals": 0,
        "entries": 0,
        "exits": 0,
        "rejected": 0,
        "errors": 0,
        "pnl": 0.0,
        "wins": 0,
        "losses": 0,
        "total_win_pnl": 0.0,
        "total_loss_pnl": 0.0,
        "rejected_scores": []
    }

    found_log = False
    for log_file in log_files:
        if strategy_name in os.path.basename(log_file):
            found_log = True
            m = parse_log_file(log_file)
            aggregated['signals'] = max(aggregated['signals'], m['signals'])
            aggregated['entries'] = max(aggregated['entries'], m['entries'])
            aggregated['exits'] = max(aggregated['exits'], m['exits'])
            aggregated['rejected'] = max(aggregated['rejected'], m['rejected'])
            aggregated['errors'] = max(aggregated['errors'], m['errors'])
            aggregated['pnl'] = m['pnl'] # Take last/max

            if m['wins'] > aggregated['wins']: aggregated['wins'] = m['wins']
            if m['losses'] > aggregated['losses']: aggregated['losses'] = m['losses']
            if m['total_win_pnl'] > aggregated['total_win_pnl']: aggregated['total_win_pnl'] = m['total_win_pnl']
            if m['total_loss_pnl'] > aggregated['total_loss_pnl']: aggregated['total_loss_pnl'] = m['total_loss_pnl']

            aggregated['rejected_scores'].extend(m['rejected_scores'])

    if not found_log:
        return None

    return aggregated

def find_param_in_content(content, param_names):
    """Finds a parameter value in file content using multiple patterns."""
    for param in param_names:
        # 1. self.param = value
        match = re.search(fr'self\.{param}\s*=\s*([\d.]+)', content)
        if match:
            return param, float(match.group(1)), "class_attr"

        # 2. parser.add_argument('--param', ... default=value)
        match = re.search(fr"parser\.add_argument\s*\(\s*['\"]--{param}['\"]\s*,.*?default\s*=\s*([\d.]+)", content, re.DOTALL)
        if match:
            return param, float(match.group(1)), "argparse"

    return None, None, None

def tune_strategy(strategy_name, metrics):
    """Determines necessary adjustments and applies them."""
    filepath = os.path.join(STRATEGIES_DIR, f"{strategy_name}.py")
    if not os.path.exists(filepath):
        return []

    with open(filepath, 'r') as f:
        content = f.read()

    adjustments = []

    # 1. Threshold Tuning
    # Potential threshold parameter names
    threshold_params = ['threshold', 'roc_threshold', 'score_threshold', 'min_score']

    rejection_rate = (metrics['rejected'] / metrics['signals']) * 100 if metrics['signals'] > 0 else 0
    if rejection_rate > 70:
        param_name, current_val, _ = find_param_in_content(content, threshold_params)

        if param_name:
            if current_val > 1.0:
                new_val = int(current_val - 3)
                if new_val < 0: new_val = 0
            else:
                new_val = round(current_val - 0.002, 4) # 0.2%
                if new_val < 0: new_val = 0

            adjustments.append({
                "param": param_name,
                "old": current_val,
                "new": new_val,
                "reason": f"High rejection rate ({rejection_rate:.1f}% > 70%). Lowering {param_name}."
            })

    # 2. Filter Refinement (Win Rate)
    win_rate = (metrics['wins'] / metrics['exits']) * 100 if metrics['exits'] > 0 else 0

    if win_rate < 60 and metrics['entries'] > 5:
        # Tighten filters: Increase threshold
        param_name, current_val, _ = find_param_in_content(content, threshold_params)

        if param_name:
            # Check for conflict
            existing_adj = next((a for a in adjustments if a['param'] == param_name), None)

            if current_val > 1.0:
                new_val = int(current_val + 5)
            else:
                new_val = round(current_val + 0.005, 4) # 0.5%

            if existing_adj:
                existing_adj['new'] = new_val
                existing_adj['reason'] = f"Low Win Rate ({win_rate:.1f}% < 60%). Tightening {param_name}, overriding rejection tuning."
            else:
                adjustments.append({
                    "param": param_name,
                    "old": current_val,
                    "new": new_val,
                    "reason": f"Low Win Rate ({win_rate:.1f}% < 60%). Tightening {param_name}."
                })

    elif win_rate > 80 and metrics['entries'] > 5:
         # Relax filters: Decrease threshold
         param_name, current_val, _ = find_param_in_content(content, threshold_params)

         if param_name:
            if current_val > 1.0:
                new_val = int(current_val - 2)
            else:
                new_val = round(current_val - 0.002, 4)

            existing_adj = next((a for a in adjustments if a['param'] == param_name), None)
            if not existing_adj:
                adjustments.append({
                    "param": param_name,
                    "old": current_val,
                    "new": new_val,
                    "reason": f"High Win Rate ({win_rate:.1f}% > 80%). Relaxing {param_name}."
                })

    # 3. Exit Optimization (R:R)
    stop_params = ['stop_pct', 'sl_pct', 'stop_loss_pct']

    avg_win = metrics['total_win_pnl'] / metrics['wins'] if metrics['wins'] > 0 else 0
    avg_loss = metrics['total_loss_pnl'] / metrics['losses'] if metrics['losses'] > 0 else 0
    rr_ratio = avg_win / avg_loss if avg_loss > 0 else (10 if avg_win > 0 else 0)

    if 0 < rr_ratio < 1.5 and metrics['entries'] > 5:
        # Tighten Stop Loss
        param_name, current_val, _ = find_param_in_content(content, stop_params)

        if param_name:
            if current_val > 0.0:
                # Assuming stop_pct is usually like 1.0, 0.5 etc.
                # If it's very small < 0.1, maybe it's ratio (0.01)
                if current_val < 0.1:
                    new_val = round(current_val - 0.002, 4)
                else:
                    new_val = round(current_val - 0.2, 2)

                if new_val < 0.05: new_val = 0.05 # Minimum floor

                adjustments.append({
                    "param": param_name,
                    "old": current_val,
                    "new": new_val,
                    "reason": f"Low R:R ({rr_ratio:.2f} < 1.5). Tightening {param_name} to improve R:R."
                })

    if adjustments:
        apply_adjustments(filepath, adjustments)

    return adjustments

def apply_adjustments(filepath, adjustments):
    """Modifies the strategy file."""
    with open(filepath, 'r') as f:
        content = f.read()

    today = datetime.now().strftime("%Y-%m-%d")

    for adj in adjustments:
        param = adj['param']
        new_val = adj['new']
        reason = adj['reason']

        # Regex for class attribute: self.param = value
        pattern_attr = fr'(self\.{param}\s*=\s*)([\d.]+)(.*)'
        # Regex for argparse: parser.add_argument('--param', ... default=value)
        pattern_arg = fr"(parser\.add_argument\s*\(\s*['\"]--{param}['\"]\s*,.*?default\s*=\s*)([\d.]+)(.*)"

        # Try replacing attribute first
        match_attr = re.search(pattern_attr, content)
        if match_attr:
            original_prefix = match_attr.group(1)
            new_line = f"{original_prefix}{new_val}  # Modified on {today}: {reason}"
            content = re.sub(pattern_attr, new_line, content, count=1)
            print(f"Applied adjustment to {filepath}: {param} (attr) -> {new_val}")
        else:
            # Try replacing argparse default
            # Argparse match might span multiple lines, but regex above handles single line matches well.
            # If it spans, we need DOTALL, which we used in find but re.sub needs care.
            # Simplified assumption: argparse definition is often one line or 'default=X' is reachable.
            # Let's use a simpler pattern targeting just 'default=...' inside an argparse block if possible,
            # or just find the line with default=... if we know it belongs to the param.

            # Robust approach: Find the specific argparse line
            # escape param name for regex
            match_arg = re.search(pattern_arg, content)
            if match_arg:
                prefix = match_arg.group(1)
                suffix = match_arg.group(3)
                # Keep the suffix (help=...) but maybe add comment at end of line?
                # Argparse usually ends with )
                # We can't easily append comment inside the call.
                # Best to just change the value.

                # Check if suffix ends with )
                # If we want to add a comment, we should add it after the closing parenthesis, or keep it clean.
                # Let's just update the value.
                new_segment = f"{prefix}{new_val}{suffix}"
                content = content.replace(match_arg.group(0), new_segment)
                print(f"Applied adjustment to {filepath}: {param} (arg default) -> {new_val}")

    with open(filepath, 'w') as f:
        f.write(content)

def calculate_score(metrics):
    """Calculates daily performance score."""
    wins = metrics['wins']
    exits = metrics['exits']
    entries = metrics['entries']
    signals = metrics['signals']
    errors = metrics['errors']

    win_rate = (wins / exits) if exits > 0 else 0

    avg_win = metrics['total_win_pnl'] / wins if wins > 0 else 0
    avg_loss = metrics['total_loss_pnl'] / metrics['losses'] if metrics['losses'] > 0 else 0
    profit_factor = metrics['total_win_pnl'] / metrics['total_loss_pnl'] if metrics['total_loss_pnl'] > 0 else (2.0 if metrics['total_win_pnl'] > 0 else 0)

    sharpe = 0.5
    if entries > 0 and metrics['pnl'] > 0:
        sharpe = 1.0

    entry_rate = (entries / signals) if signals > 0 else 0
    error_free_rate = 1.0 - (errors / entries) if entries > 0 else 1.0
    if error_free_rate < 0: error_free_rate = 0

    score = (win_rate * 0.3) + (min(profit_factor, 5.0) * 0.3) + (sharpe * 0.2) + (entry_rate * 0.1) + (error_free_rate * 0.1)

    return {
        "score": round(score, 2),
        "win_rate": round(win_rate * 100, 1),
        "profit_factor": round(profit_factor, 2)
    }

def generate_report(results, all_adjustments, ranked_strategies):
    """Generates Markdown report."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    report = []
    report.append(f"📊 END-OF-DAY REPORT - {date_str}\n")

    report.append("📈 TODAY'S PERFORMANCE SUMMARY:")
    report.append("Strategy | Signals | Entries | Wins | WR% | PF | Score | Status")
    report.append("---------|---------|---------|------|-----|----|-------|--------")

    for item in ranked_strategies:
        strategy = item['strategy']
        metrics = results[strategy]
        score = item['score']
        wr = item['win_rate']
        pf = item['profit_factor']
        status = "✓" if score > 1.0 else "✗"

        row = f"{strategy[:15]:<15} | {metrics['signals']:<7} | {metrics['entries']:<7} | {metrics['wins']:<4} | {wr:<3}% | {pf:<2} | {score:<5} | {status}"
        report.append(row)

    report.append("\n🔧 INCREMENTAL IMPROVEMENTS APPLIED:")
    if all_adjustments:
        for strategy, adjs in all_adjustments.items():
            report.append(f"1. {strategy}")
            for adj in adjs:
                report.append(f"   - Changed: {adj['param']} from {adj['old']} to {adj['new']}")
                report.append(f"   - Reason: {adj['reason']}")
    else:
        report.append("No improvements applied.")

    report.append("\n📊 STRATEGY RANKING (Top 5 for Tomorrow):")
    for i, item in enumerate(ranked_strategies[:5], 1):
        strat = item['strategy']
        score = item['score']
        action = "Start/Restart" if score > 0.8 else "Review"
        report.append(f"{i}. {strat} - Score: {score} - [Action: {action}]")

    report.append("\n🚀 DEPLOYMENT PLAN:")
    to_stop = [s['strategy'] for s in ranked_strategies if s['score'] <= 0.8]
    to_start = [s['strategy'] for s in ranked_strategies if s['score'] > 0.8]

    report.append(f"- Stop: {', '.join(to_stop) if to_stop else 'None'}")
    report.append(f"- Start: {', '.join(to_start) if to_start else 'None'}")
    report.append(f"- Restart: {', '.join(list(all_adjustments.keys()))}")

    report.append("\n⚠️ ISSUES FOUND:")
    issues_found = False
    for strat, res in results.items():
        if res['errors'] > 0:
            report.append(f"- {strat}: {res['errors']} errors found. Check logs.")
            issues_found = True
    if not issues_found:
        report.append("- No critical errors found.")

    report.append("\n💡 INSIGHTS FOR TOMORROW:")
    report.append("- [Automated] Strategies with score < 0.8 have been flagged for review or stop.")
    if all_adjustments:
        report.append("- [Automated] Parameter adjustments applied to improve WR/RR.")

    return "\n".join(report)

def save_rankings(ranked_strategies):
    """Saves rankings to CSV."""
    os.makedirs(RANKINGS_DIR, exist_ok=True)
    filepath = os.path.join(RANKINGS_DIR, "strategy_rankings.csv")

    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["rank", "strategy", "score", "total_trades"])
        for i, item in enumerate(ranked_strategies, 1):
            writer.writerow([i, item['strategy'], item['score'], item['total_trades']])

    print(f"Rankings saved to {filepath}")

def generate_deployment_script(ranked_strategies, all_strategies):
    """Generates a shell script to deploy top strategies."""
    os.makedirs(os.path.dirname(DEPLOY_SCRIPT_PATH), exist_ok=True)

    to_deploy = [s['strategy'] for s in ranked_strategies if s['score'] > 0.8]

    with open(DEPLOY_SCRIPT_PATH, 'w') as f:
        f.write("#!/bin/bash\n")
        f.write("# Auto-generated deployment script based on daily optimization\n\n")

        f.write("# Load environment variables\n")
        f.write("if [ -f .env ]; then\n")
        f.write("    export $(cat .env | xargs)\n")
        f.write("fi\n\n")

        f.write(f"LOG_DIR={LOG_DIRS[0]}\n")
        f.write("mkdir -p $LOG_DIR\n\n")

        f.write("echo 'Stopping strategies...'\n")
        f.write("pkill -f 'strategies/scripts/.*.py' || true\n")
        f.write("\n")

        f.write("echo 'Starting optimized strategies...'\n\n")

        for strategy in to_deploy:
            script_path = os.path.join(STRATEGIES_DIR, f"{strategy}.py")
            log_path = os.path.join(LOG_DIRS[0], f"{strategy}_live.log")

            if os.path.exists(script_path):
                f.write(f"echo 'Starting {strategy}...'\n")
                f.write(f"nohup python3 {script_path} > {log_path} 2>&1 &\n")
                f.write(f"echo 'Started {strategy} with PID $!'\n\n")
            else:
                 f.write(f"echo 'Warning: Script {script_path} not found.'\n")

        f.write("echo 'Deployment complete.'\n")

    os.chmod(DEPLOY_SCRIPT_PATH, 0o755)
    print(f"Deployment script generated at {DEPLOY_SCRIPT_PATH}")

def main():
    log_files = get_today_logs()

    if not log_files:
        print("No logs found for today.")
        return

    strategies = set()
    for log_file in log_files:
        filename = os.path.basename(log_file)
        name_part = filename
        if '_20' in filename:
            name_part = filename.split('_20')[0]
        elif '.' in filename:
            name_part = filename.split('.')[0]

        if name_part not in ['openalgo', 'alerts', 'monitor']:
            strategies.add(name_part)

    results = {}
    all_adjustments = {}
    ranked_strategies = []

    for strategy in strategies:
        metrics = analyze_strategy(strategy, log_files)
        if not metrics:
            continue

        results[strategy] = metrics

        adjustments = tune_strategy(strategy, metrics)
        if adjustments:
            all_adjustments[strategy] = adjustments

        score_data = calculate_score(metrics)
        ranked_strategies.append({
            "strategy": strategy,
            "score": score_data['score'],
            "win_rate": score_data['win_rate'],
            "profit_factor": score_data['profit_factor'],
            "total_trades": metrics['entries']
        })

    ranked_strategies.sort(key=lambda x: x['score'], reverse=True)

    report = generate_report(results, all_adjustments, ranked_strategies)
    print(report)

    save_rankings(ranked_strategies)
    generate_deployment_script(ranked_strategies, strategies)

if __name__ == "__main__":
    main()
