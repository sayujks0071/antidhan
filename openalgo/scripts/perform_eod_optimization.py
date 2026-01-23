import os
import re
import glob
from datetime import datetime
from collections import defaultdict
import json

# Configuration
LOG_DIR = "openalgo/log/strategies"
STRATEGIES_DIR = "openalgo/strategies/scripts"

def get_today_logs():
    """Finds log files for the current date."""
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    pattern = os.path.join(LOG_DIR, f"*{date_str}*.log")
    return glob.glob(pattern)

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
            metrics_match = re.search(r'\[METRICS\]\s+signals=(\d+)\s+entries=(\d+)\s+exits=(\d+)\s+rejected=(\d+)\s+errors=(\d+)\s+pnl=([\d.-]+)', line)
            if metrics_match:
                metrics['signals'] = max(metrics['signals'], int(metrics_match.group(1)))
                metrics['entries'] = max(metrics['entries'], int(metrics_match.group(2)))
                metrics['exits'] = max(metrics['exits'], int(metrics_match.group(3)))
                metrics['rejected'] = max(metrics['rejected'], int(metrics_match.group(4)))
                metrics['errors'] = max(metrics['errors'], int(metrics_match.group(5)))
                metrics['pnl'] = max(metrics['pnl'], float(metrics_match.group(6)))

            rejected_match = re.search(r'\[REJECTED\]\s+symbol=(\S+)\s+score=([\d.]+)\s+reason=(\S+)', line)
            if rejected_match:
                metrics['rejected_reasons'][rejected_match.group(3)] += 1
                metrics['rejected_scores'].append(float(rejected_match.group(2)))

            exit_match = re.search(r'\[EXIT\].*pnl=([\d.-]+)', line)
            if exit_match:
                pnl = float(exit_match.group(1))
                if pnl > 0:
                    metrics['wins'] += 1
                    metrics['total_win_pnl'] += pnl
                elif pnl < 0:
                    metrics['losses'] += 1
                    metrics['total_loss_pnl'] += abs(pnl)

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

    for log_file in log_files:
        if strategy_name in os.path.basename(log_file):
            m = parse_log_file(log_file)
            aggregated['signals'] = max(aggregated['signals'], m['signals'])
            aggregated['entries'] = max(aggregated['entries'], m['entries'])
            aggregated['exits'] = max(aggregated['exits'], m['exits'])
            aggregated['rejected'] = max(aggregated['rejected'], m['rejected'])
            aggregated['errors'] = max(aggregated['errors'], m['errors'])
            aggregated['pnl'] += m['pnl']
            aggregated['wins'] += m['wins']
            aggregated['losses'] += m['losses']
            aggregated['total_win_pnl'] += m['total_win_pnl']
            aggregated['total_loss_pnl'] += m['total_loss_pnl']
            aggregated['rejected_scores'].extend(m['rejected_scores'])

    return aggregated

def tune_strategy(strategy_name, metrics):
    """Determines necessary adjustments and applies them."""
    filepath = os.path.join(STRATEGIES_DIR, f"{strategy_name}.py")
    if not os.path.exists(filepath):
        return []

    adjustments = []

    # 1. Threshold Tuning
    rejection_rate = (metrics['rejected'] / metrics['signals']) * 100 if metrics['signals'] > 0 else 0
    if rejection_rate > 70:
        with open(filepath, 'r') as f:
            content = f.read()
            match = re.search(r'self.threshold\s*=\s*([\d.]+)', content)
            if match:
                current_threshold = float(match.group(1))
                new_threshold = int(current_threshold - 3) # Lower by 3 points as per rule
                if new_threshold < 0: new_threshold = 0

                adjustments.append({
                    "param": "threshold",
                    "old": current_threshold,
                    "new": new_threshold,
                    "reason": f"High rejection rate ({rejection_rate:.1f}% > 70%). Lowering threshold by 3 points."
                })

    # 2. Exit Optimization (R:R)
    avg_win = metrics['total_win_pnl'] / metrics['wins'] if metrics['wins'] > 0 else 0
    avg_loss = metrics['total_loss_pnl'] / metrics['losses'] if metrics['losses'] > 0 else 0
    rr_ratio = avg_win / avg_loss if avg_loss > 0 else (10 if avg_win > 0 else 0)

    if 0 < rr_ratio < 1.5:
        # Tighten Stop Loss
        with open(filepath, 'r') as f:
            content = f.read()
            match = re.search(r'self.stop_pct\s*=\s*([\d.]+)', content)
            if match:
                current_stop = float(match.group(1))
                new_stop = round(current_stop - 0.2, 2) # Tighten by 0.2%
                if new_stop < 0.1: new_stop = 0.1

                adjustments.append({
                    "param": "stop_pct",
                    "old": current_stop,
                    "new": new_stop,
                    "reason": f"Low R:R ({rr_ratio:.2f} < 1.5). Tightening stop_pct to improve R:R."
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

        # Regex to find parameter definition and consume rest of line (comments)
        pattern = fr'(self\.{param}\s*=\s*)([\d.]+)(.*)'

        match = re.search(pattern, content)
        if match:
            original_prefix = match.group(1)
            # Reconstruct line without old comment
            new_line = f"{original_prefix}{new_val}  # Modified on {today}: {reason}"
            content = content.replace(match.group(0), new_line, 1)
            print(f"Applied adjustment to {filepath}: {param} -> {new_val}")

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

    sharpe = 1.0 # Placeholder

    entry_rate = (entries / signals) if signals > 0 else 0
    error_free_rate = 1.0 - (errors / entries) if entries > 0 else 1.0

    score = (win_rate * 0.3) + (profit_factor * 0.3) + (sharpe * 0.2) + (entry_rate * 0.1) + (error_free_rate * 0.1)

    return {
        "score": round(score, 2),
        "win_rate": round(win_rate * 100, 1),
        "profit_factor": round(profit_factor, 2)
    }

def generate_report(results, all_adjustments):
    """Generates Markdown report."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    report = []
    report.append(f"📊 END-OF-DAY REPORT - {date_str}\n")

    report.append("📈 TODAY'S PERFORMANCE SUMMARY:")
    report.append("Strategy | Signals | Entries | Wins | WR% | PF | Score | Status")
    report.append("---------|---------|---------|------|-----|----|-------|--------")

    ranked_strategies = []

    for strategy, metrics in results.items():
        score_data = calculate_score(metrics)
        score = score_data['score']
        wr = score_data['win_rate']
        pf = score_data['profit_factor']

        status = "✓" if score > 0.5 else "✗"

        row = f"{strategy:<15} | {metrics['signals']:<7} | {metrics['entries']:<7} | {metrics['wins']:<4} | {wr:<3}% | {pf:<2} | {score:<5} | {status}"
        report.append(row)

        ranked_strategies.append((strategy, score))

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
    ranked_strategies.sort(key=lambda x: x[1], reverse=True)
    for i, (strat, score) in enumerate(ranked_strategies[:5], 1):
        action = "Start/Restart" if score > 0.5 else "Review"
        report.append(f"{i}. {strat} - Score: {score} - [Action: {action}]")

    report.append("\n🚀 DEPLOYMENT PLAN:")
    to_start = [s[0] for s in ranked_strategies if s[1] > 0.5]
    report.append(f"- Start/Restart: {', '.join(to_start)}")

    return "\n".join(report)

def main():
    log_files = get_today_logs()

    strategies = set()
    for log_file in log_files:
        filename = os.path.basename(log_file)
        parts = filename.split('_20')
        if len(parts) > 0:
            strategies.add(parts[0])

    results = {}
    all_adjustments = {}

    for strategy in strategies:
        metrics = analyze_strategy(strategy, log_files)
        results[strategy] = metrics

        adjustments = tune_strategy(strategy, metrics)
        if adjustments:
            all_adjustments[strategy] = adjustments

    report = generate_report(results, all_adjustments)
    print(report)

if __name__ == "__main__":
    main()
