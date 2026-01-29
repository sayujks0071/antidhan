#!/usr/bin/env python3
"""
Comprehensive Trade Monitoring Script
════════════════════════════════════════════════════════════════════════════

Monitors ongoing trades, parses logs, tracks positions, and provides
fine-tuning recommendations based on real-time trading activity.

Features:
- Real-time process status (actual running processes)
- Log parsing for entries/exits/PnL
- Performance metrics tracking
- Fine-tuning recommendations
"""

import json
import subprocess
import re
from urllib import request
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

try:
    import psutil
except ImportError:
    psutil = None

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "strategies/strategy_configs.json"
ENV_PATH = BASE_DIR / "strategies/strategy_env.json"
LOG_DIR = BASE_DIR / "strategies/logs"
ALT_LOG_DIR = BASE_DIR / "log/strategies"
BASE_URL = "http://127.0.0.1:5001"
ALERT_LOG = BASE_DIR / "log/alerts.log"

# Strategy name mappings (from process command to strategy ID)
STRATEGY_NAME_MAP = {
    'mcx_commodity_momentum': 'mcx_commodity_momentum_strategy',
    'ai_hybrid_reversion_breakout': 'ai_hybrid_reversion_breakout',
    'advanced_ml_momentum': 'advanced_ml_momentum_strategy_20260120112512',
    'supertrend_vwap': 'supertrend_vwap_strategy_20260120112816',
    'orb_strategy': 'orb_strategy',
    'trend_pullback': 'trend_pullback_strategy',
    'delta_neutral_iron_condor': 'delta_neutral_iron_condor_nifty',
    'options_ranker': 'options_ranker_strategy',
}

# -----------------------------------------------------------------------------
# Notification Manager
# -----------------------------------------------------------------------------

class NotificationManager:
    """
    Manages real-time alerts and notifications across multiple channels.
    """
    def __init__(self):
        self.alert_file = ALERT_LOG
        self.alert_file.parent.mkdir(parents=True, exist_ok=True)

        # Load configuration for external notifiers if available
        self.telegram_token = os.environ.get("TELEGRAM_TOKEN")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    def send_alert(self, message: str, level: str = "WARNING", category: str = "GENERAL"):
        """
        Dispatch alert to configured channels.

        Args:
            message: The alert message
            level: INFO, WARNING, CRITICAL
            category: TRADE, RISK, SYSTEM, DATA
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_msg = f"[{timestamp}] [{level}] [{category}] {message}"

        # 1. Log to File
        try:
            with open(self.alert_file, "a") as f:
                f.write(formatted_msg + "\n")
        except Exception as e:
            print(f"Failed to write to alert log: {e}")

        # 2. Console Output (High visibility)
        if level == "CRITICAL":
            print(f"\033[91m{formatted_msg}\033[0m") # Red
        elif level == "WARNING":
            print(f"\033[93m{formatted_msg}\033[0m") # Yellow
        else:
            print(formatted_msg)

        # 3. External Channels (Mock/Placeholder)
        if level in ["CRITICAL", "WARNING"]:
            self._send_telegram(formatted_msg)
            self._send_email(formatted_msg)

    def _send_telegram(self, message: str):
        """Placeholder for Telegram integration"""
        if self.telegram_token and self.telegram_chat_id:
            # Implement actual API call here
            # requests.post(f"https://api.telegram.org/bot{self.telegram_token}/sendMessage", ...)
            pass

    def _send_email(self, message: str):
        """Placeholder for Email integration"""
        pass

# Initialize global manager
notifier = NotificationManager()


def get_ist_time():
    """Get current IST time."""
    return datetime.now().strftime("%H:%M:%S IST")


def find_running_strategy_processes() -> Dict[str, Dict]:
    """Find all running strategy processes and match them to strategy IDs."""
    running = {}
    
    if not psutil:
        # Fallback: use ps command
        try:
            result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
            lines = result.stdout.split('\n')
            for line in lines:
                if 'python' in line.lower() and 'strategies/scripts/' in line:
                    parts = line.split()
                    if len(parts) > 1:
                        pid = parts[1]
                        cmd_str = ' '.join(parts[10:]).lower()
                        script_path = None
                        for token in parts[10:]:
                            if 'strategies/scripts/' in token and token.endswith('.py'):
                                script_path = token
                                break
                        # Try mapping
                        matched = False
                        for key, strategy_id in STRATEGY_NAME_MAP.items():
                            if key in cmd_str:
                                running[strategy_id] = {
                                    'pid': int(pid),
                                    'name': 'python',
                                    'cmdline': parts[10:],
                                    'script_path': script_path,
                                    'start_time': 'Unknown'
                                }
                                matched = True
                                break
                        # Fallback to script basename
                        if not matched and script_path:
                            fallback_id = Path(script_path).stem
                            running[fallback_id] = {
                                'pid': int(pid),
                                'name': 'python',
                                'cmdline': parts[10:],
                                'script_path': script_path,
                                'start_time': 'Unknown'
                            }
        except Exception:
            pass
        return running
    
    # Find all Python processes running strategy scripts
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline', [])
            if not cmdline:
                continue
            
            # Check if it's a Python process running a strategy
            cmd_str = ' '.join(cmdline).lower()
            
            # Match strategy scripts
            for key, strategy_id in STRATEGY_NAME_MAP.items():
                if key in cmd_str and 'strategy' in cmd_str:
                    # Extract script path
                    script_path = None
                    for arg in cmdline:
                        if 'strategy' in arg.lower() and arg.endswith('.py'):
                            script_path = arg
                            break
                    
                    running[strategy_id] = {
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'cmdline': cmdline,
                        'script_path': script_path,
                        'start_time': datetime.fromtimestamp(proc.create_time()).strftime('%Y-%m-%d %H:%M:%S')
                    }
                    break
            else:
                # Fallback: use script basename if a strategy script is found
                script_path = None
                for arg in cmdline:
                    if 'strategies/scripts/' in arg and arg.endswith('.py'):
                        script_path = arg
                        break
                if script_path:
                    fallback_id = Path(script_path).stem
                    running[fallback_id] = {
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'cmdline': cmdline,
                        'script_path': script_path,
                        'start_time': datetime.fromtimestamp(proc.create_time()).strftime('%Y-%m-%d %H:%M:%S')
                    }
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    
    return running


def find_strategy_log_file(strategy_id: str) -> Optional[Path]:
    """Find the most recent log file for a strategy."""
    # Try both log directories
    for log_dir in [LOG_DIR, ALT_LOG_DIR]:
        if not log_dir.exists():
            continue
        
        # Try various patterns
        patterns = [
            f"*{strategy_id}*.log",
            f"*{strategy_id.replace('_', '*')}*.log",
        ]
        
        # Also try matching by partial name
        if '_' in strategy_id:
            parts = strategy_id.split('_')
            patterns.append(f"*{parts[0]}*{parts[-1]}*.log")
        
        # Special handling for MCX
        if 'mcx' in strategy_id.lower():
            patterns.extend([
                "*mcx*enhanced*.log",
                "*mcx*commodity*.log",
                "*mcx*commodity*momentum*.log",
            ])
        
        for pattern in patterns:
            log_files = list(log_dir.glob(pattern))
            if log_files:
                # Return most recent
                return max(log_files, key=lambda p: p.stat().st_mtime)
    
    return None


def parse_log_for_entries(log_file: Path, lines: int = 500) -> Dict:
    """Parse log file for trade entries, exits, and metrics."""
    if not log_file or not log_file.exists():
        return {
            'entries': [],
            'exits': [],
            'active_positions': [],
            'rejected_signals': [],
            'errors': [],
            'metrics': {}
        }
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            log_lines = f.readlines()[-lines:]  # Last N lines
    except Exception as e:
        return {'error': f"Failed to read log: {e}"}
    
    entries = []
    exits = []
    active_positions = []
    rejected_signals = []
    errors = []
    metrics = {
        'signals': 0,
        'entries': 0,
        'exits': 0,
        'errors': 0,
        'rejected': 0,
        'daily_pnl': 0.0
    }
    
    # Patterns for parsing
    entry_patterns = [
        re.compile(r'\[ENTRY\]\s+symbol=(\S+)\s+entry=([\d.]+)\s+order_id=(\S+)', re.I),
        re.compile(r'🎯\s+(LONG|SHORT)\s+ENTRY:\s+(\S+)', re.I),
        re.compile(r'✅\s+Order placed successfully for (\S+):\s+Order ID (\S+)', re.I),
        re.compile(r'Opened.*position.*(\S+).*entry.*?([\d.]+)', re.I),
    ]
    
    exit_patterns = [
        re.compile(r'\[EXIT\]\s+symbol=(\S+)\s+exit=([\d.]+)\s+pnl=([\d.-]+)\s+reason=(\S+)', re.I),
        re.compile(r'Position closed.*PnL:\s+([\d.-]+)', re.I),
        re.compile(r'Exiting position.*(\S+).*PnL:\s+([\d.-]+)', re.I),
    ]
    
    rejected_patterns = [
        re.compile(r'\[REJECTED\]\s+symbol=(\S+)\s+score=([\d.]+)\s+reason=(.+)', re.I),
        re.compile(r'⚠️\s+(\S+):\s+Score\s+([\d.]+)\s+<\s+.*threshold', re.I),
        re.compile(r'⚠️\s+(\S+):\s+.*rejecting entry', re.I),
    ]
    
    error_patterns = [
        re.compile(r'\[ERROR\]', re.I),
        re.compile(r'Error|ERROR|Failed|FAILED|Exception|Traceback', re.I),
    ]
    
    metrics_patterns = [
        re.compile(r'\[METRICS\]\s+signals=(\d+)\s+entries=(\d+)\s+exits=(\d+)\s+rejected=(\d+)\s+errors=(\d+)\s+pnl=([\d.-]+)', re.I),
        re.compile(r'\[METRICS\]\s+signals=(\d+)\s+entries=(\d+)\s+exits=(\d+)\s+errors=(\d+)\s+pnl=([\d.-]+)', re.I),
    ]
    
    position_patterns = [
        re.compile(r'\[POSITION\]\s+symbol=(\S+)\s+entry=([\d.]+)\s+current=([\d.-]+)\s+pnl=([\d.-]+)\s+tp1=([\d.-]+)\s+tp2=([\d.-]+)\s+tp3=([\d.-]+)\s+sl=([\d.-]+)\s+qty=([\d/]+)', re.I),
        re.compile(r'Active:\s+(\S+)\s+\((\d+)/(\d+)\)', re.I),
        re.compile(r'\[(\d+:\d+:\d+)\]\s+Active:\s+(\S+)', re.I),
    ]
    
    for line in log_lines:
        line_lower = line.lower()
        
        # Parse entries
        for pattern in entry_patterns:
            match = pattern.search(line)
            if match:
                if 'symbol=' in line:
                    entries.append({
                        'symbol': match.group(1),
                        'entry_price': float(match.group(2)),
                        'order_id': match.group(3),
                        'time': extract_time_from_line(line),
                        'line': line.strip()
                    })
                else:
                    entries.append({
                        'symbol': match.group(2) if len(match.groups()) > 1 else match.group(1),
                        'entry_price': None,
                        'order_id': match.group(2) if 'Order ID' in line else None,
                        'time': extract_time_from_line(line),
                        'line': line.strip()
                    })
                metrics['entries'] += 1
                break
        
        # Parse exits
        for pattern in exit_patterns:
            match = pattern.search(line)
            if match:
                if 'pnl=' in line:
                    exits.append({
                        'symbol': match.group(1),
                        'exit_price': float(match.group(2)),
                        'pnl': float(match.group(3)),
                        'reason': match.group(4) if len(match.groups()) > 3 else 'Unknown',
                        'time': extract_time_from_line(line),
                        'line': line.strip()
                    })
                else:
                    pnl_match = re.search(r'PnL:\s+([\d.-]+)', line)
                    exits.append({
                        'symbol': match.group(1),
                        'exit_price': None,
                        'pnl': float(pnl_match.group(1)) if pnl_match else 0.0,
                        'reason': 'Unknown',
                        'time': extract_time_from_line(line),
                        'line': line.strip()
                    })
                metrics['exits'] += 1
                if pnl_match:
                    metrics['daily_pnl'] += float(pnl_match.group(1))
                break
        
        # Parse rejected signals
        for pattern in rejected_patterns:
            match = pattern.search(line)
            if match:
                rejected_signals.append({
                    'symbol': match.group(1),
                    'score': float(match.group(2)) if len(match.groups()) > 1 and match.group(2).replace('.', '').isdigit() else None,
                    'reason': match.group(3) if len(match.groups()) > 2 else 'Threshold',
                    'time': extract_time_from_line(line),
                    'line': line.strip()
                })
                metrics['rejected'] += 1
                break
        
        # Parse errors
        for pattern in error_patterns:
            if pattern.search(line) and 'error' in line_lower:
                errors.append({
                    'message': line.strip()[:200],
                    'time': extract_time_from_line(line),
                    'line': line.strip()
                })
                metrics['errors'] += 1
                break
        
        # Parse metrics
        for pattern in metrics_patterns:
            match = pattern.search(line)
            if match:
                metrics['signals'] = max(metrics['signals'], int(match.group(1)))
                metrics['entries'] = max(metrics['entries'], int(match.group(2)))
                metrics['exits'] = max(metrics['exits'], int(match.group(3)))
                if len(match.groups()) >= 6:
                    metrics['rejected'] = max(metrics['rejected'], int(match.group(4)))
                    metrics['errors'] = max(metrics['errors'], int(match.group(5)))
                    metrics['daily_pnl'] = max(metrics['daily_pnl'], float(match.group(6)))
                else:
                    metrics['errors'] = max(metrics['errors'], int(match.group(4)))
                    metrics['daily_pnl'] = max(metrics['daily_pnl'], float(match.group(5)))
                break
        
        # Parse active positions
        for pattern in position_patterns:
            match = pattern.search(line)
            if match:
                if line.startswith("[POSITION]"):
                    active_positions.append({
                        'symbol': match.group(1),
                        'entry_price': float(match.group(2)),
                        'current_price': float(match.group(3)),
                        'pnl': float(match.group(4)),
                        'tp1': float(match.group(5)),
                        'tp2': float(match.group(6)),
                        'tp3': float(match.group(7)),
                        'sl': float(match.group(8)),
                        'qty': match.group(9),
                        'time': extract_time_from_line(line),
                        'line': line.strip()
                    })
                elif len(match.groups()) == 3:
                    active_positions.append({
                        'symbol': match.group(1),
                        'current': int(match.group(2)),
                        'max': int(match.group(3)),
                        'time': extract_time_from_line(line),
                        'line': line.strip()
                    })
                else:
                    active_positions.append({
                        'symbol': match.group(2),
                        'current': 1,
                        'max': 1,
                        'time': match.group(1),
                        'line': line.strip()
                    })
                break
    
    # Count signals (look for signal generation patterns)
    signal_count = len([l for l in log_lines if 'signal' in l.lower() and ('buy' in l.lower() or 'sell' in l.lower())])
    metrics['signals'] = max(metrics['signals'], signal_count)
    
    return {
        'entries': entries[-10:],  # Last 10 entries
        'exits': exits[-10:],  # Last 10 exits
        'active_positions': active_positions[-5:] if active_positions else [],
        'rejected_signals': rejected_signals[-20:],  # Last 20 rejected
        'errors': errors[-10:],  # Last 10 errors
        'metrics': metrics
    }


def extract_time_from_line(line: str) -> Optional[str]:
    """Extract timestamp from log line."""
    # Try various time patterns
    time_patterns = [
        r'\[(\d{2}:\d{2}:\d{2})\]',
        r'(\d{2}:\d{2}:\d{2})',
        r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',
    ]
    
    for pattern in time_patterns:
        match = re.search(pattern, line)
        if match:
            return match.group(1)
    
    return None


def load_api_key() -> Optional[str]:
    """Load API key from env or strategy_env.json."""
    api_key = os.environ.get("OPENALGO_APIKEY")
    if api_key:
        return api_key
    if ENV_PATH.exists():
        try:
            data = json.loads(ENV_PATH.read_text())
            for _, vars_dict in data.items():
                if isinstance(vars_dict, dict) and vars_dict.get("OPENALGO_APIKEY"):
                    return vars_dict["OPENALGO_APIKEY"]
        except Exception:
            return None
    return None


def fetch_positionbook(api_key: str) -> List[Dict]:
    """Fetch broker positionbook via API."""
    try:
        payload = json.dumps({"apikey": api_key}).encode("utf-8")
        req = request.Request(
            f"{BASE_URL}/api/v1/positionbook",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)
        if isinstance(data, dict) and data.get("status") == "success":
            return data.get("data", [])
    except Exception:
        return []
    return []


def generate_fine_tuning_recommendations(analysis: Dict) -> List[str]:
    """Generate fine-tuning recommendations based on analysis."""
    recommendations = []
    
    for strategy_id, data in analysis.items():
        if 'log_data' not in data:
            continue
        
        log_data = data['log_data']
        metrics = log_data.get('metrics', {})
        rejected = log_data.get('rejected_signals', [])
        
        # Check entry rate
        signals = metrics.get('signals', 0)
        entries = metrics.get('entries', 0)
        rejected_count = metrics.get('rejected', 0)
        
        if signals > 0:
            entry_rate = (entries / signals) * 100 if signals > 0 else 0
            if entry_rate < 20 and rejected_count > 5:
                recommendations.append(
                    f"⚠️  {strategy_id}: Low entry rate ({entry_rate:.1f}%). "
                    f"Consider lowering entry threshold. {rejected_count} signals rejected."
                )
        
        # Check error rate
        errors = metrics.get('errors', 0)
        if errors > 5:
            msg = f"🔴 {strategy_id}: High error count ({errors}). Check logs for issues."
            recommendations.append(msg)
            notifier.send_alert(msg, level="CRITICAL", category="SYSTEM")
        
        # Analyze rejected signals
        if rejected:
            # Group by reason
            reasons = defaultdict(int)
            scores = []
            for sig in rejected:
                reason = sig.get('reason', 'Unknown')
                reasons[reason] += 1
                if sig.get('score'):
                    scores.append(sig['score'])
            
            if scores:
                avg_score = sum(scores) / len(scores)
                if avg_score > 35 and 'threshold' in str(reasons).lower():
                    recommendations.append(
                        f"📊 {strategy_id}: Average rejected score {avg_score:.1f}. "
                        f"Consider lowering threshold by 2-3 points."
                    )
    
    return recommendations


def main():
    """Main monitoring function."""
    print("=" * 80)
    print("📊 COMPREHENSIVE TRADE MONITORING")
    print("=" * 80)
    print(f"Time: {get_ist_time()}\n")
    
    # Find running processes
    running_processes = find_running_strategy_processes()
    
    print(f"🔍 Found {len(running_processes)} running strategy processes\n")
    
    # Load configs
    configs = {}
    if CONFIG_PATH.exists():
        try:
            configs = json.loads(CONFIG_PATH.read_text())
        except Exception as e:
            print(f"⚠️  Failed to load configs: {e}\n")
    
    # Analyze each running strategy
    analysis = {}
    
    for strategy_id, proc_info in running_processes.items():
        print(f"📈 Analyzing: {strategy_id} (PID: {proc_info['pid']})")
        
        # Find log file
        log_file = find_strategy_log_file(strategy_id)
        
        if log_file:
            print(f"   📝 Log: {log_file.name}")
            log_data = parse_log_for_entries(log_file)
        else:
            print(f"   ⚠️  No log file found")
            log_data = {}
        
        analysis[strategy_id] = {
            'process': proc_info,
            'log_file': str(log_file) if log_file else None,
            'log_data': log_data
        }

    # Fetch broker positions
    api_key = load_api_key()
    broker_positions = []
    if api_key:
        broker_positions = fetch_positionbook(api_key)
    broker_mcx = [p for p in broker_positions if p.get("exchange") == "MCX" and p.get("quantity")]
    
    print("\n" + "=" * 80)
    print("📊 PERFORMANCE METRICS")
    print("=" * 80)

    if broker_mcx:
        symbols = [f"{p.get('symbol')}({p.get('quantity')})" for p in broker_mcx]
        print(f"\nBroker MCX Positions ({len(broker_mcx)}): " + ", ".join(symbols))
    
    for strategy_id, data in analysis.items():
        if 'log_data' not in data:
            continue
        
        log_data = data['log_data']
        metrics = log_data.get('metrics', {})
        
        print(f"\n{strategy_id}:")
        print(f"  Signals: {metrics.get('signals', 0)}")
        print(f"  Entries: {metrics.get('entries', 0)}")
        print(f"  Exits: {metrics.get('exits', 0)}")
        print(f"  Rejected: {metrics.get('rejected', 0)}")
        print(f"  Errors: {metrics.get('errors', 0)}")
        print(f"  Daily P&L: ₹{metrics.get('daily_pnl', 0.0):.2f}")
        
        # Show active positions
        active_positions = log_data.get('active_positions', [])
        if active_positions:
            latest = active_positions[-1]
            if "entry_price" in latest:
                print(
                    f"  Position: {latest.get('symbol', 'Unknown')} "
                    f"Entry=₹{latest.get('entry_price', 0):.2f} "
                    f"Current=₹{latest.get('current_price', 0):.2f} "
                    f"P&L=₹{latest.get('pnl', 0.0):.2f} "
                    f"SL=₹{latest.get('sl', 0):.2f} Qty={latest.get('qty', 'N/A')}"
                )
            else:
                print(f"  Active Positions: {latest.get('symbol', 'Unknown')} ({latest.get('current', 0)}/{latest.get('max', 0)})")
        
        # Show recent entries
        entries = log_data.get('entries', [])
        if entries:
            latest_entry = entries[-1]
            print(f"  Latest Entry: {latest_entry.get('symbol', 'Unknown')} @ ₹{latest_entry.get('entry_price', 'N/A')}")
        
        # Show recent exits
        exits = log_data.get('exits', [])
        if exits:
            latest_exit = exits[-1]
            print(f"  Latest Exit: {latest_exit.get('symbol', 'Unknown')} P&L: ₹{latest_exit.get('pnl', 0.0):.2f}")

        # Show last error
        errors = log_data.get('errors', [])
        if errors:
            last_error = errors[-1]
            print(f"  Last Error: {last_error.get('message', '')[:120]}")

        # Show top rejection reasons
        rejected = log_data.get('rejected_signals', [])
        if rejected:
            reason_counts = defaultdict(int)
            for r in rejected:
                reason_counts[r.get('reason', 'Unknown')] += 1
            top_reasons = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            print("  Top Rejections: " + ", ".join([f"{r}({c})" for r, c in top_reasons]))
    
    print("\n" + "=" * 80)
    print("🎯 FINE-TUNING RECOMMENDATIONS")
    print("=" * 80)
    
    recommendations = generate_fine_tuning_recommendations(analysis)
    
    if recommendations:
        for rec in recommendations:
            print(f"\n{rec}")
    else:
        print("\n✅ No immediate fine-tuning recommendations. Strategies appear healthy.")
    
    print("\n" + "=" * 80)
    print("✅ Monitoring complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
