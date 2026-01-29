#!/usr/bin/env python3
"""Check live trading status and broker connection."""
import json
from pathlib import Path
import subprocess

print("=" * 80)
print("LIVE TRADING STATUS CHECK")
print("=" * 80)

# Check running strategies
config_path = Path("/Users/mac/dyad-apps/openalgo/strategies/strategy_configs.json")
if config_path.exists():
    configs = json.loads(config_path.read_text())
    running = [(k, v) for k, v in configs.items() if v.get('is_running')]
    
    print(f"\n✅ Running Strategies: {len(running)}")
    for sid, cfg in running:
        pid = cfg.get('pid')
        name = cfg.get('name', sid)
        print(f"  - {name} (PID: {pid})")
        
        # Check if process is actually running
        if pid:
            try:
                result = subprocess.run(['ps', '-p', str(pid)], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"    ✅ Process active")
                else:
                    print(f"    ⚠️  Process not found")
            except:
                pass

# Check environment variables
env_path = Path("/Users/mac/dyad-apps/openalgo/strategies/strategy_env.json")
if env_path.exists():
    env_data = json.loads(env_path.read_text())
    print(f"\n✅ Environment Variables Configured:")
    for sid, vars in env_data.items():
        if 'OPENALGO_APIKEY' in vars:
            print(f"  - {sid}: OPENALGO_APIKEY set")
else:
    print("\n⚠️  No environment variables file found")

# Check recent logs for errors
print(f"\n📋 Recent Log Activity:")
log_dir = Path("/Users/mac/dyad-apps/openalgo/log/strategies")
if log_dir.exists():
    log_files = sorted(log_dir.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)[:3]
    for log_file in log_files:
        print(f"\n  {log_file.name}:")
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                # Show last 5 lines
                for line in lines[-5:]:
                    if line.strip():
                        print(f"    {line.strip()}")
        except:
            print("    (Could not read log)")

print("\n" + "=" * 80)
print("RECOMMENDATIONS:")
print("=" * 80)
print("1. Verify broker connection at: http://127.0.0.1:5001/auth/broker")
print("2. Check if broker access token is valid (may need daily refresh)")
print("3. Verify market is open (9:15 AM - 3:30 PM IST)")
print("4. Check broker API credentials in environment variables")
print("=" * 80)
