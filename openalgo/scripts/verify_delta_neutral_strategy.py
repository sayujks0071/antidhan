#!/usr/bin/env python3
"""Verify Delta Neutral Strategy is properly configured"""
import json
from pathlib import Path

config_path = Path('strategies/strategy_configs.json')
env_path = Path('strategies/strategy_env.json')

print("=" * 80)
print("DELTA NEUTRAL STRATEGY VERIFICATION")
print("=" * 80)

# Load configs
with open(config_path) as f:
    configs = json.load(f)

with open(env_path) as f:
    env_data = json.load(f)

strategy_id = 'delta_neutral_iron_condor_nifty_20260123131614'

if strategy_id in configs:
    cfg = configs[strategy_id]
    print(f"✅ Strategy found in configs")
    print(f"   ID: {strategy_id}")
    print(f"   Name: {cfg.get('name')}")
    print(f"   File: {cfg.get('file_path')}")
    print(f"   User ID: {cfg.get('user_id')}")
    print(f"   Created: {cfg.get('created_at')}")
    
    # Check file exists
    file_path = Path(cfg.get('file_path', ''))
    if not file_path.is_absolute():
        file_path = Path('strategies/scripts') / file_path.name
    
    if file_path.exists():
        print(f"   ✅ File exists: {file_path}")
    else:
        print(f"   ❌ File missing: {file_path}")
else:
    print(f"❌ Strategy NOT found in configs")

if strategy_id in env_data:
    if 'OPENALGO_APIKEY' in env_data[strategy_id]:
        print(f"✅ API Key is set")
    else:
        print(f"❌ API Key missing")
else:
    print(f"❌ Strategy NOT found in env file")

print()
print("=" * 80)
print("TROUBLESHOOTING:")
print("=" * 80)
print("If you don't see it in the web UI:")
print()
print("1. RESTART FLASK SERVER:")
print("   - Stop the Flask server (Ctrl+C in terminal)")
print("   - Start it again: python3 app.py")
print()
print("2. CLEAR BROWSER CACHE:")
print("   - Hard refresh: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)")
print("   - Or clear cache in browser settings")
print()
print("3. CHECK YOU'RE LOGGED IN:")
print("   - Make sure you're logged in with your OpenAlgo username")
print("   - URL: http://127.0.0.1:5001/python")
print()
print("4. VERIFY IN BROWSER CONSOLE:")
print("   - Press F12 to open developer tools")
print("   - Check Console tab for errors")
print("   - Check Network tab to see if /python endpoint loads correctly")
print("=" * 80)
