#!/usr/bin/env python3
"""CLI script to run backtests on historical data (Wrapper around canonical runner)"""
import sys
import subprocess

def main():
    # Pass all arguments to the canonical runner
    cmd = [sys.executable, "-m", "packages.core.runner", "backtest"] + sys.argv[1:]
    
    # If data-dir is not provided, check if docs folder exists, otherwise use fixtures
    if "--data-dir" not in sys.argv:
        import os
        if not os.path.exists("docs/NSE OPINONS DATA"):
            cmd.extend(["--data-dir", "tests/fixtures"])

    subprocess.run(cmd)

if __name__ == "__main__":
    main()
