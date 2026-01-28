#!/usr/bin/env python3
"""
Check Background Optimization Status
Shows running optimization processes and their progress
"""
import subprocess
import json
from pathlib import Path
from datetime import datetime

def get_optimization_processes():
    """Get all running optimization processes"""
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True,
        text=True
    )
    
    processes = []
    for line in result.stdout.split('\n'):
        if 'optimize_strategies.py' in line and 'grep' not in line:
            parts = line.split()
            if len(parts) >= 11:
                processes.append({
                    'pid': parts[1],
                    'cpu': parts[2],
                    'mem': parts[3],
                    'started': f"{parts[8]} {parts[9]}",
                    'command': ' '.join(parts[10:])
                })
    
    return processes

def get_latest_results():
    """Get latest optimization results"""
    results_dir = Path(__file__).parent.parent / "strategies" / "optimization_results"
    if not results_dir.exists():
        return []
    
    files = list(results_dir.glob("*.json"))
    results = []
    for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
        results.append({
            'name': f.name,
            'modified': datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            'size': f.stat().st_size
        })
    
    return results

def check_optimization_log():
    """Check optimization log file"""
    log_file = Path(__file__).parent.parent / "strategies" / "optimization.log"
    if not log_file.exists():
        return None
    
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    return {
        'exists': True,
        'lines': len(lines),
        'last_10_lines': lines[-10:] if len(lines) > 10 else lines
    }

def main():
    print("=" * 80)
    print("  BACKGROUND OPTIMIZATION STATUS")
    print("=" * 80)
    print()
    
    # Check running processes
    processes = get_optimization_processes()
    
    if processes:
        print(f"✅ Found {len(processes)} optimization process(es) running:\n")
        
        for i, proc in enumerate(processes, 1):
            print(f"Process {i}:")
            print(f"  PID: {proc['pid']}")
            print(f"  CPU: {proc['cpu']}%")
            print(f"  Memory: {proc['mem']}%")
            print(f"  Started: {proc['started']}")
            print(f"  Command: {proc['command'][:100]}...")
            print()
    else:
        print("❌ No optimization processes running")
        print()
    
    # Check latest results
    print("-" * 80)
    print("Latest Optimization Results:")
    print("-" * 80)
    
    results = get_latest_results()
    if results:
        for result in results:
            print(f"  📄 {result['name']}")
            print(f"     Modified: {result['modified']}")
            print(f"     Size: {result['size']} bytes")
            print()
    else:
        print("  No optimization results found")
        print()
    
    # Check optimization log
    print("-" * 80)
    print("Optimization Log:")
    print("-" * 80)
    
    log_info = check_optimization_log()
    if log_info:
        print(f"  Log file exists: ✅")
        print(f"  Total lines: {log_info['lines']}")
        print()
        print("  Last 10 lines:")
        for line in log_info['last_10_lines']:
            print(f"    {line.rstrip()}")
    else:
        print("  No optimization log file found")
        print()
    
    # Summary
    print("=" * 80)
    print("  SUMMARY")
    print("=" * 80)
    
    if processes:
        print(f"✅ Optimization is RUNNING")
        print(f"   Active processes: {len(processes)}")
        print(f"   Latest results: {len(results)} file(s)")
    else:
        print("❌ Optimization is NOT running")
        print("   To start optimization:")
        print("   cd openalgo/strategies")
        print("   python3 scripts/optimize_strategies.py --strategies all --method hybrid")
    
    print()

if __name__ == "__main__":
    main()
