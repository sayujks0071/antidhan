#!/usr/bin/env python3
"""
Real-time Strategy Monitoring Script
Monitors running strategies and displays their status, logs, and performance
"""

import json
import subprocess
import time
import os
from pathlib import Path
from datetime import datetime
import glob
import sys

CONFIG_FILE = Path(__file__).parent.parent / "strategies" / "strategy_configs.json"
LOGS_DIR = Path(__file__).parent.parent / "log" / "strategies"

def clear_screen():
    """Clear terminal screen"""
    os.system('clear' if os.name != 'nt' else 'cls')

def get_process_info(pid):
    """Get detailed process information"""
    try:
        result = subprocess.run(['ps', '-p', str(pid), '-o', 'pid,pcpu,pmem,etime,rss,vsz,command'], 
                              capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                parts = lines[1].split(None, 6)
                if len(parts) >= 6:
                    return {
                        'pid': parts[0],
                        'cpu': parts[1],
                        'mem': parts[2],
                        'etime': parts[3],
                        'rss': parts[4],  # Resident Set Size (KB)
                        'vsz': parts[5],  # Virtual Size (KB)
                        'command': parts[6] if len(parts) > 6 else ''
                    }
        return None
    except Exception as e:
        return None

def get_latest_log_entries(sid, n=5):
    """Get latest log entries for a strategy"""
    log_pattern = str(LOGS_DIR / f"{sid}_*.log")
    logs = sorted(glob.glob(log_pattern), reverse=True)
    if logs:
        try:
            with open(logs[0], 'r') as f:
                lines = f.readlines()
                return [line.strip() for line in lines[-n:] if line.strip()]
        except Exception as e:
            pass
    return []

def check_process_alive(pid):
    """Check if process is actually running"""
    if not pid:
        return False
    try:
        result = subprocess.run(['ps', '-p', str(pid)], 
                              capture_output=True, text=True, timeout=1)
        return result.returncode == 0
    except:
        return False

def format_size(kb):
    """Format size in KB to human readable"""
    if kb < 1024:
        return f"{kb} KB"
    elif kb < 1024 * 1024:
        return f"{kb/1024:.2f} MB"
    else:
        return f"{kb/(1024*1024):.2f} GB"

def monitor_loop(refresh_interval=5):
    """Main monitoring loop"""
    try:
        while True:
            clear_screen()
            
            if not CONFIG_FILE.exists():
                print("❌ Strategy config file not found!")
                time.sleep(refresh_interval)
                continue
            
            with open(CONFIG_FILE) as f:
                configs = json.load(f)
            
            running = {sid: config for sid, config in configs.items() 
                      if config.get('is_running', False)}
            
            print("=" * 80)
            print("  🔴 LIVE STRATEGY MONITOR")
            print(f"  Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
            print("=" * 80)
            print()
            
            if not running:
                print("⚠️  No strategies currently running")
                print()
                print("Start strategies at: http://127.0.0.1:5001/python/")
            else:
                print(f"✅ {len(running)} Strategy(ies) Running")
                print()
                
                for i, (sid, config) in enumerate(sorted(running.items()), 1):
                    name = config.get('name', sid)
                    pid = config.get('pid')
                    started_at = config.get('last_started', 'Unknown')
                    
                    # Verify process is actually running
                    is_alive = check_process_alive(pid)
                    status_icon = "✅" if is_alive else "⚠️"
                    
                    print("─" * 80)
                    print(f"{status_icon} [{i}] {name}")
                    print("─" * 80)
                    
                    if pid:
                        proc_info = get_process_info(pid)
                        if proc_info and is_alive:
                            print(f"   PID:        {proc_info['pid']}")
                            print(f"   CPU Usage: {proc_info['cpu']}%")
                            print(f"   Memory:    {proc_info['mem']}% ({format_size(int(proc_info['rss']))})")
                            print(f"   Runtime:   {proc_info['etime']}")
                            print(f"   Virtual:   {format_size(int(proc_info['vsz']))}")
                        else:
                            print(f"   ⚠️  PID {pid} - Process not found or exited")
                    else:
                        print("   ⚠️  No PID recorded")
                    
                    print(f"   Started:    {started_at}")
                    
                    # Check for errors
                    error_msg = config.get('error_message')
                    if error_msg:
                        print(f"   ❌ Error:    {error_msg[:80]}")
                    
                    # Latest log entries
                    log_entries = get_latest_log_entries(sid, 3)
                    if log_entries:
                        print("   Recent Logs:")
                        for entry in log_entries:
                            # Show only last 100 chars
                            display = entry[-100:] if len(entry) > 100 else entry
                            # Extract timestamp if present
                            if ' - ' in display:
                                parts = display.split(' - ', 2)
                                if len(parts) >= 3:
                                    print(f"      [{parts[0]}] {parts[2][:70]}")
                                else:
                                    print(f"      {display[:80]}")
                            else:
                                print(f"      {display[:80]}")
                    else:
                        print("   No recent log entries")
                    
                    print()
            
            print("=" * 80)
            print("  QUICK ACTIONS")
            print("=" * 80)
            print()
            print("📊 Dashboard: http://127.0.0.1:5001/dashboard")
            print("📋 Manage:    http://127.0.0.1:5001/python/")
            print("📁 Logs:      log/strategies/")
            print()
            print(f"⏱️  Refreshing every {refresh_interval} seconds... (Press Ctrl+C to stop)")
            
            time.sleep(refresh_interval)
            
    except KeyboardInterrupt:
        print("\n\n👋 Monitoring stopped")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    refresh = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    monitor_loop(refresh)
