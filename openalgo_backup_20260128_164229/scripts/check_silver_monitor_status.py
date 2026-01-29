#!/usr/bin/env python3
"""
Quick status checker for Silver Mini Position Monitor
"""
import subprocess
from pathlib import Path
from datetime import datetime

def check_monitor_status():
    """Check if monitor is running and show recent logs"""
    print("=" * 60)
    print("Silver Mini Position Monitor Status")
    print("=" * 60)
    print()
    
    # Check if process is running
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True,
        text=True
    )
    
    monitor_running = "monitor_silver_position" in result.stdout
    
    if monitor_running:
        print("✅ Monitor Status: RUNNING")
        print()
        
        # Find PID
        for line in result.stdout.split('\n'):
            if 'monitor_silver_position' in line and 'grep' not in line:
                parts = line.split()
                if parts:
                    print(f"   PID: {parts[1]}")
                    print(f"   CPU: {parts[2]}%")
                    print(f"   MEM: {parts[3]}%")
    else:
        print("❌ Monitor Status: NOT RUNNING")
        print()
        print("To start: cd openalgo && OPENAI_API_KEY='your-key' nohup python3 scripts/monitor_silver_position.py > log/silver_monitor_output.log 2>&1 &")
    
    print()
    print("-" * 60)
    print("Recent Log Entries:")
    print("-" * 60)
    
    log_file = Path(__file__).parent.parent / "log" / "silver_position_monitor.log"
    if log_file.exists():
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                recent_lines = lines[-20:] if len(lines) > 20 else lines
                for line in recent_lines:
                    print(line.rstrip())
        except Exception as e:
            print(f"Error reading log: {e}")
    else:
        print("Log file not found yet (monitor may have just started)")
    
    print()
    print("=" * 60)
    print(f"Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

if __name__ == "__main__":
    check_monitor_status()
