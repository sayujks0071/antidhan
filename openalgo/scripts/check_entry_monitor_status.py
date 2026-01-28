#!/usr/bin/env python3
"""Quick status checker for Entry Opportunities Monitor"""
import subprocess
from pathlib import Path
from datetime import datetime

def check_status():
    """Check monitor status and show recent activity"""
    print("=" * 70)
    print("Entry Opportunities Monitor Status")
    print("=" * 70)
    print()
    
    # Check if process is running
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True,
        text=True
    )
    
    monitor_running = "monitor_entry_opportunities" in result.stdout
    
    if monitor_running:
        print("✅ Monitor Status: RUNNING")
        print()
        
        # Find PID
        for line in result.stdout.split('\n'):
            if 'monitor_entry_opportunities' in line and 'grep' not in line:
                parts = line.split()
                if parts:
                    print(f"   PID: {parts[1]}")
                    print(f"   CPU: {parts[2]}%")
                    print(f"   MEM: {parts[3]}%")
    else:
        print("❌ Monitor Status: NOT RUNNING")
        print()
        print("To start:")
        print("  cd openalgo && OPENAI_API_KEY='your-key' nohup python3 scripts/monitor_entry_opportunities.py > log/entry_opportunities_output.log 2>&1 &")
    
    print()
    print("-" * 70)
    print("Recent Activity:")
    print("-" * 70)
    
    log_file = Path(__file__).parent.parent / "log" / "entry_opportunities_monitor.log"
    output_file = Path(__file__).parent.parent / "log" / "entry_opportunities_output.log"
    
    for log_path, label in [(log_file, "Monitor Log"), (output_file, "Output Log")]:
        if log_path.exists():
            try:
                with open(log_path, 'r') as f:
                    lines = f.readlines()
                    recent_lines = lines[-15:] if len(lines) > 15 else lines
                    if recent_lines:
                        print(f"\n{label}:")
                        for line in recent_lines:
                            print(f"   {line.rstrip()}")
            except Exception as e:
                print(f"Error reading {label}: {e}")
    
    print()
    print("=" * 70)
    print(f"Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

if __name__ == "__main__":
    check_status()
