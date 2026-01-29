#!/usr/bin/env python3
"""
Restart all strategies that had 403 errors (now fixed)
- mcx_elite_strategy (API key fixed)
- mcx_neural_strategy (API key fixed)
- advanced_ml_momentum_strategy (PR #48 changes)
- natural_gas_clawdbot_strategy (API key fixed)
- crude_oil_enhanced_strategy (API key fixed)
"""
import json
import requests
import time
import re
from pathlib import Path

BASE_URL = "http://127.0.0.1:5001"
CONFIG_FILE = Path(__file__).parent.parent / "strategies" / "strategy_configs.json"

# Strategies to restart (with fixes applied)
STRATEGIES_TO_RESTART = [
    {
        "name": "mcx_elite_strategy",
        "reason": "API key fixed"
    },
    {
        "name": "mcx_neural_strategy",
        "reason": "API key fixed"
    },
    {
        "name": "advanced_ml_momentum_strategy",
        "reason": "PR #48 changes (relaxed entry conditions)"
    },
    {
        "name": "natural_gas_clawdbot_strategy",
        "reason": "API key fixed"
    },
    {
        "name": "crude_oil_enhanced_strategy",
        "reason": "API key fixed"
    }
]

def extract_csrf_token(html):
    """Extract CSRF token from HTML"""
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return match.group(1) if match else None

def login_and_get_session():
    """Login and return session"""
    session = requests.Session()
    
    # Get login page
    login_page = session.get(f"{BASE_URL}/auth/login")
    csrf_token = extract_csrf_token(login_page.text)
    
    # Login
    login_data = {
        "username": "sayujks0071",
        "password": "Apollo@20417"
    }
    if csrf_token:
        login_data["csrf_token"] = csrf_token
    
    login_resp = session.post(f"{BASE_URL}/auth/login", data=login_data, allow_redirects=True)
    
    # Check if login successful
    if login_resp.status_code == 200:
        try:
            data = login_resp.json()
            if data.get("status") == "success":
                return session
        except:
            pass
    
    # Check if redirected to dashboard/broker page
    if '/auth/broker' in login_resp.url or '/dashboard' in login_resp.url:
        return session
    
    return None

def find_strategy_id(configs, strategy_name):
    """Find strategy ID by name"""
    for strategy_id, config in configs.items():
        if strategy_name.lower() in config.get('name', '').lower():
            return strategy_id
    return None

def stop_strategy(session, strategy_id):
    """Stop a strategy"""
    resp = session.post(f"{BASE_URL}/python/stop/{strategy_id}")
    if resp.status_code == 200:
        try:
            data = resp.json()
            return data.get('success', False), data.get('message', '')
        except:
            return True, "Stopped"
    return False, f"HTTP {resp.status_code}"

def start_strategy(session, strategy_id):
    """Start a strategy"""
    resp = session.post(f"{BASE_URL}/python/start/{strategy_id}")
    if resp.status_code == 200:
        try:
            data = resp.json()
            return data.get('success', False), data.get('message', '')
        except:
            return True, "Started"
    return False, f"HTTP {resp.status_code}"

def main():
    print("=" * 80)
    print("  RESTART ALL FIXED STRATEGIES")
    print("=" * 80)
    print()
    print("Strategies to restart:")
    for i, strategy in enumerate(STRATEGIES_TO_RESTART, 1):
        print(f"  {i}. {strategy['name']} - {strategy['reason']}")
    print()
    
    # Login
    print("Logging in...")
    session = login_and_get_session()
    if not session:
        print("❌ Login failed")
        print("\nPlease restart manually via Web UI:")
        print("  1. Go to: http://127.0.0.1:5001/python")
        print("  2. Login if needed")
        print("  3. For each strategy, click 'Start'")
        return
    
    print("✅ Logged in")
    print()
    
    # Load configs
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            configs = json.load(f)
    else:
        print("❌ Strategy configs not found")
        return
    
    # Process each strategy
    print("Finding and restarting strategies...")
    print()
    
    results = []
    
    for strategy_info in STRATEGIES_TO_RESTART:
        strategy_name = strategy_info['name']
        reason = strategy_info['reason']
        
        print(f"Strategy: {strategy_name}")
        print(f"  Reason: {reason}")
        print("-" * 80)
        
        # Find strategy ID
        strategy_id = find_strategy_id(configs, strategy_name)
        
        if not strategy_id:
            print(f"  ⚠️  Strategy not found: {strategy_name}")
            results.append({'name': strategy_name, 'status': 'not_found'})
            print()
            continue
        
        print(f"  Found ID: {strategy_id}")
        
        # Check if running
        is_running = configs[strategy_id].get('is_running', False)
        
        # Stop if running
        if is_running:
            print("  1. Stopping...", end=" ")
            success, msg = stop_strategy(session, strategy_id)
            if success:
                print(f"✅ {msg}")
            else:
                print(f"⚠️  {msg}")
            time.sleep(2)
        else:
            print("  1. Already stopped ✅")
        
        # Start strategy
        print("  2. Starting...", end=" ")
        success, msg = start_strategy(session, strategy_id)
        if success:
            print(f"✅ {msg}")
            results.append({'name': strategy_name, 'status': 'started'})
        else:
            print(f"❌ {msg}")
            results.append({'name': strategy_name, 'status': 'failed', 'error': msg})
        
        print()
    
    # Summary
    print("=" * 80)
    print("  SUMMARY")
    print("=" * 80)
    print()
    
    started = [r for r in results if r.get('status') == 'started']
    failed = [r for r in results if r.get('status') == 'failed']
    not_found = [r for r in results if r.get('status') == 'not_found']
    
    print(f"✅ Started: {len(started)}")
    for r in started:
        print(f"   - {r['name']}")
    
    if failed:
        print(f"\n❌ Failed: {len(failed)}")
        for r in failed:
            print(f"   - {r['name']}: {r.get('error', 'Unknown error')}")
    
    if not_found:
        print(f"\n⚠️  Not Found: {len(not_found)}")
        for r in not_found:
            print(f"   - {r['name']}")
    
    print()
    print("=" * 80)
    print("✅ Restart complete!")
    print("=" * 80)
    print()
    print("Check status at: http://127.0.0.1:5001/python")
    print("Monitor logs to verify strategies are running without errors")

if __name__ == "__main__":
    main()
