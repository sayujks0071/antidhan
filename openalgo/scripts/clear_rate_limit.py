#!/usr/bin/env python3
"""
Clear rate limits by restarting the Flask server.
Rate limits are stored in memory and reset on server restart.
"""
import subprocess
import sys
import os
from pathlib import Path

print("=" * 80)
print("RATE LIMIT CLEARANCE TOOL")
print("=" * 80)

# Check if server is running
print("\n1. Checking if OpenAlgo server is running...")
try:
    result = subprocess.run(['lsof', '-ti:5001'], capture_output=True, text=True)
    if result.returncode == 0:
        pids = result.stdout.strip().split('\n')
        print(f"   ✅ Server running on port 5001 (PIDs: {', '.join(pids)})")
        
        print("\n2. Options to clear rate limit:")
        print("   Option A: Restart the server (clears in-memory rate limits)")
        print("   Option B: Wait for rate limit window to reset:")
        print("      - Per-minute limit: 60 seconds")
        print("      - Per-hour limit: 60 minutes")
        
        response = input("\n   Restart server to clear rate limit? (y/n): ").strip().lower()
        
        if response == 'y':
            print("\n   Stopping server...")
            for pid in pids:
                try:
                    subprocess.run(['kill', pid], check=True)
                    print(f"   ✅ Stopped process {pid}")
                except:
                    print(f"   ⚠️  Could not stop process {pid}")
            
            print("\n   To restart the server, run:")
            print("   cd /Users/mac/dyad-apps/openalgo")
            print("   source venv/bin/activate")
            print("   FLASK_PORT=5001 python app.py")
            print("\n   Or use your existing server startup command.")
        else:
            print("\n   Rate limits will reset automatically:")
            print("   - Per-minute limit: Wait 60 seconds")
            print("   - Per-hour limit: Wait up to 60 minutes")
            print("\n   Current limits:")
            print("   - LOGIN_RATE_LIMIT_MIN: 5 per minute")
            print("   - LOGIN_RATE_LIMIT_HOUR: 25 per hour")
    else:
        print("   ⚠️  Server not running on port 5001")
        print("   Rate limits are cleared when server is not running.")
        
except Exception as e:
    print(f"   ⚠️  Error checking server: {e}")

print("\n" + "=" * 80)
print("RATE LIMIT INFORMATION:")
print("=" * 80)
print("Rate limits are stored in memory and reset when:")
print("1. The Flask server restarts")
print("2. The rate limit time window expires (1 min or 1 hour)")
print("\nCurrent limits:")
print("- 5 login attempts per minute")
print("- 25 login attempts per hour")
print("=" * 80)
