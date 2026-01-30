#!/usr/bin/env python3
"""
Monitor running strategies and their logs.
"""
import os
import sys
import time
import subprocess
import re
from datetime import datetime

# Adjust paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR) # openalgo/
LOG_DIR = os.path.join(REPO_ROOT, "log", "strategies")

def get_running_strategies():
    """Find running strategy processes."""
    strategies = []
    try:
        # pgrep -af returns PID and command line
        cmd = ["pgrep", "-af", "strategies/scripts"]
        output = subprocess.check_output(cmd).decode("utf-8")

        for line in output.splitlines():
            if "monitor_strategies.py" in line: continue

            parts = line.split()
            pid = parts[0]
            cmdline = " ".join(parts[1:])

            # Extract script name
            script_match = re.search(r'([\w_]+\.py)', cmdline)
            script_name = script_match.group(1) if script_match else "unknown"

            # Extract symbol
            symbol_match = re.search(r'--symbol\s+(\w+)', cmdline)
            symbol = symbol_match.group(1) if symbol_match else "UNKNOWN"

            # Extract Logfile
            log_match = re.search(r'--logfile\s+([^\s]+)', cmdline)
            logfile = log_match.group(1) if log_match else None

            strategies.append({
                "pid": pid,
                "script": script_name,
                "symbol": symbol,
                "logfile": logfile,
                "cmd": cmdline
            })

    except subprocess.CalledProcessError:
        pass

    return strategies

def tail_log(logfile, lines=5):
    if not logfile or not os.path.exists(logfile):
        return ["Log file not found"]
    try:
        cmd = ["tail", "-n", str(lines), logfile]
        return subprocess.check_output(cmd).decode("utf-8").splitlines()
    except:
        return ["Error reading log"]

def main():
    print(f"--- OpenAlgo Strategy Monitor --- {datetime.now()}")
    strategies = get_running_strategies()

    if not strategies:
        print("No strategies running.")
        return

    print(f"{'PID':<8} {'SYMBOL':<10} {'STRATEGY':<30} {'LOG FILE'}")
    print("-" * 80)

    for s in strategies:
        log_display = s['logfile'] if s['logfile'] else "N/A"
        print(f"{s['pid']:<8} {s['symbol']:<10} {s['script']:<30} {log_display}")

        # If we have a logfile, show last line
        if s['logfile']:
            logs = tail_log(s['logfile'], 1)
            if logs:
                print(f"  Last Log: {logs[0]}")
        print("")

if __name__ == "__main__":
    main()
