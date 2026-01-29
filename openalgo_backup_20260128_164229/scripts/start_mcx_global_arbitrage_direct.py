#!/usr/bin/env python3
"""
Start MCX Global Arbitrage Strategy directly (bypassing Web UI)
This avoids 403 errors from Web UI authentication
"""
import os
import sys
import subprocess
from pathlib import Path

# Set environment variables
API_KEY = "5258b9b7d21a17843c83da367919c659579ae050889bd3aa3f1f386a90c19163"
API_HOST = "http://127.0.0.1:5001"

# Strategy file
STRATEGY_FILE = Path(__file__).parent.parent / "strategies" / "scripts" / "mcx_global_arbitrage_strategy.py"

def main():
    print("=" * 80)
    print("  START MCX GLOBAL ARBITRAGE STRATEGY DIRECTLY")
    print("=" * 80)
    print()
    
    if not STRATEGY_FILE.exists():
        print(f"❌ Strategy file not found: {STRATEGY_FILE}")
        return
    
    print(f"Strategy: {STRATEGY_FILE.name}")
    print(f"API Key: {API_KEY[:30]}...")
    print(f"API Host: {API_HOST}")
    print()
    
    # Set environment variables
    env = os.environ.copy()
    env['OPENALGO_APIKEY'] = API_KEY
    env['OPENALGO_HOST'] = API_HOST
    env['SYMBOL'] = os.getenv('SYMBOL', 'REPLACE_ME')
    env['GLOBAL_SYMBOL'] = os.getenv('GLOBAL_SYMBOL', 'REPLACE_ME_GLOBAL')
    
    print("Starting strategy...")
    print("Press Ctrl+C to stop")
    print("-" * 80)
    print()
    
    try:
        # Run strategy directly
        subprocess.run(
            [sys.executable, '-u', str(STRATEGY_FILE.absolute())],
            env=env
        )
    except KeyboardInterrupt:
        print("\n\nStrategy stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting strategy: {e}")

if __name__ == "__main__":
    main()
