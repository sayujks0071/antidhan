#!/usr/bin/env python3
"""
Enhanced strategy status check script.
Shows running status, API key status, restart needs, and recent errors.
"""
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List

CONFIG_PATH = Path("/Users/mac/dyad-apps/openalgo/strategies/strategy_configs.json")
ENV_PATH = Path("/Users/mac/dyad-apps/openalgo/strategies/strategy_env.json")
LOG_DIR = Path("/Users/mac/dyad-apps/openalgo/log/strategies")

# Strategies that need restart due to bug fixes
STRATEGIES_NEEDING_RESTART = {
    "orb_strategy",
    "trend_pullback_strategy"
}


def get_ist_time():
    """Get current IST time."""
    return datetime.now().strftime("%H:%M:%S IST")


def check_process_status(pid):
    """Check if process is running."""
    if not pid:
        return False
    try:
        result = subprocess.run(['ps', '-p', str(pid)], capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False


def get_recent_errors(strategy_id: str, limit: int = 5) -> List[str]:
    """Get recent errors from strategy logs."""
    errors = []
    if not LOG_DIR.exists():
        return errors
    
    # Find log files for this strategy
    log_files = list(LOG_DIR.glob(f"*{strategy_id}*.log"))
    if not log_files:
        return errors
    
    # Get most recent log file
    log_file = max(log_files, key=lambda p: p.stat().st_mtime)
    
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
            # Look for errors in last 50 lines
            for line in lines[-50:]:
                line_lower = line.lower()
                if 'error' in line_lower or 'failed' in line_lower or '403' in line_lower or 'forbidden' in line_lower:
                    errors.append(line.strip())
                    if len(errors) >= limit:
                        break
    except Exception:
        pass
    
    return errors


def main():
    """Main function."""
    print("=" * 80)
    print("STRATEGY STATUS CHECK")
    print("=" * 80)
    print(f"Time: {get_ist_time()}")
    
    # Load configs
    if not CONFIG_PATH.exists():
        print("\n❌ Strategy configs not found")
        return
    
    configs = json.loads(CONFIG_PATH.read_text())
    
    # Load env data
    env_data = {}
    if ENV_PATH.exists():
        env_data = json.loads(ENV_PATH.read_text())
    
    # Analyze strategies
    running = []
    stopped = []
    needs_api_key = []
    needs_restart = []
    
    for strategy_id, config in configs.items():
        name = config.get('name', strategy_id)
        is_running = config.get('is_running', False)
        pid = config.get('pid')
        
        # Verify process is actually running
        if is_running and pid:
            is_running = check_process_status(pid)
        
        has_api_key = strategy_id in env_data and 'OPENALGO_APIKEY' in env_data[strategy_id]
        needs_restart_flag = strategy_id in STRATEGIES_NEEDING_RESTART
        
        status_info = {
            'id': strategy_id,
            'name': name,
            'is_running': is_running,
            'pid': pid,
            'has_api_key': has_api_key,
            'needs_restart': needs_restart_flag
        }
        
        if is_running:
            running.append(status_info)
        else:
            stopped.append(status_info)
        
        if not has_api_key:
            needs_api_key.append(status_info)
        
        if needs_restart_flag:
            needs_restart.append(status_info)
    
    # Print summary
    print(f"\n📊 Summary:")
    print(f"  Total strategies: {len(configs)}")
    print(f"  Running: {len(running)}")
    print(f"  Stopped: {len(stopped)}")
    print(f"  Need API key: {len(needs_api_key)}")
    print(f"  Need restart: {len(needs_restart)}")
    
    # Running strategies
    if running:
        print(f"\n✅ Running Strategies ({len(running)}):")
        for s in running:
            status = "✅ ACTIVE" if s['is_running'] else "⚠️  INACTIVE"
            api_status = "✅" if s['has_api_key'] else "❌"
            restart_status = "⚠️  NEEDS RESTART" if s['needs_restart'] else ""
            print(f"  {s['name']} (PID: {s['pid']}) - {status} | API Key: {api_status} {restart_status}")
    
    # Stopped strategies
    if stopped:
        print(f"\n⏸️  Stopped Strategies ({len(stopped)}):")
        for s in stopped[:10]:  # Show first 10
            api_status = "✅" if s['has_api_key'] else "❌"
            restart_status = "⚠️  NEEDS RESTART" if s['needs_restart'] else ""
            print(f"  {s['name']} - API Key: {api_status} {restart_status}")
        if len(stopped) > 10:
            print(f"  ... and {len(stopped) - 10} more")
    
    # Strategies needing API key
    if needs_api_key:
        print(f"\n🔑 Strategies Needing API Key ({len(needs_api_key)}):")
        for s in needs_api_key:
            print(f"  - {s['name']} ({s['id']})")
    
    # Strategies needing restart
    if needs_restart:
        print(f"\n🔄 Strategies Needing Restart ({len(needs_restart)}):")
        for s in needs_restart:
            print(f"  - {s['name']} ({s['id']})")
    
    # Recent errors
    print(f"\n⚠️  Recent Errors:")
    error_found = False
    for strategy_id, config in list(configs.items())[:5]:  # Check first 5 strategies
        errors = get_recent_errors(strategy_id, limit=2)
        if errors:
            error_found = True
            name = config.get('name', strategy_id)
            print(f"  {name}:")
            for err in errors:
                print(f"    - {err[:100]}...")
    
    if not error_found:
        print("  No recent errors found")
    
    print("\n" + "=" * 80)
    print("✅ Status check complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
