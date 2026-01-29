#!/usr/bin/env python3
"""
Restart strategies updated in PR #48
- advanced_ml_momentum_strategy (relaxed entry conditions)
- mcx_global_arbitrage_strategy (argument parsing fixes)
"""
import json
import requests
import time
import re
from pathlib import Path

BASE_URL = "http://127.0.0.1:5001"
CONFIG_FILE = Path(__file__).parent.parent / "strategies" / "strategy_configs.json"

# Strategies to restart
STRATEGY_NAMES = [
    "advanced_ml_momentum_strategy",
    "mcx_global_arbitrage_strategy"
]

def extract_csrf_token(html):
    """Extract CSRF token from HTML"""
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return match.group(1) if match else None

def fetch_csrf(session, url):
    """Fetch CSRF token from a URL"""
    resp = session.get(url, allow_redirects=True)
    if not resp.ok:
        return None
    return extract_csrf_token(resp.text)

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

def find_strategy_id(session, strategy_name):
    """Find strategy ID by name"""
    try:
        resp = session.get(f"{BASE_URL}/python")
        if resp.status_code == 200:
            # Try to get strategy configs
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r') as f:
                    configs = json.load(f)
                
                # Search for strategy by name
                for strategy_id, config in configs.items():
                    if strategy_name.lower() in config.get('name', '').lower():
                        return strategy_id
    except Exception as e:
        print(f"Error finding strategy: {e}")
    
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
    print("  RESTART STRATEGIES FROM PR #48")
    print("=" * 80)
    print()
    print("Strategies to restart:")
    print("  1. advanced_ml_momentum_strategy (relaxed entry conditions)")
    print("  2. mcx_global_arbitrage_strategy (argument parsing fixes)")
    print()
    
    # Login
    print("Logging in...")
    session = login_and_get_session()
    if not session:
        print("❌ Login failed")
        print("\nPlease restart manually via Web UI:")
        print("  1. Go to: http://127.0.0.1:5001/python")
        print("  2. Login if needed")
        print("  3. For each strategy:")
        print("     - Click 'Stop' (if running)")
        print("     - Wait 2 seconds")
        print("     - Click 'Start'")
        return
    
    print("✅ Logged in")
    print()
    
    # Load configs to find strategy IDs
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            configs = json.load(f)
    else:
        print("❌ Strategy configs not found")
        return
    
    # Process each strategy
    print("Finding and restarting strategies...")
    print()
    
    for strategy_name in STRATEGY_NAMES:
        print(f"Strategy: {strategy_name}")
        print("-" * 80)
        
        # Find strategy ID
        strategy_id = None
        for sid, config in configs.items():
            if strategy_name.lower() in config.get('name', '').lower():
                strategy_id = sid
                print(f"  Found ID: {strategy_id}")
                break
        
        if not strategy_id:
            print(f"  ⚠️  Strategy not found: {strategy_name}")
            print()
            continue
        
        # Stop strategy
        print("  1. Stopping...", end=" ")
        success, msg = stop_strategy(session, strategy_id)
        if success:
            print(f"✅ {msg}")
        else:
            print(f"⚠️  {msg} (may already be stopped)")
        time.sleep(2)
        
        # Start strategy
        print("  2. Starting...", end=" ")
        success, msg = start_strategy(session, strategy_id)
        if success:
            print(f"✅ {msg}")
        else:
            print(f"❌ {msg}")
        
        print()
    
    print("=" * 80)
    print("✅ Restart complete!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("  1. Check status at: http://127.0.0.1:5001/python")
    print("  2. Monitor logs for order placement:")
    print("     - advanced_ml_momentum_strategy: Should see more signals with relaxed conditions")
    print("     - mcx_global_arbitrage_strategy: Should start without 403 errors")
    print()

if __name__ == "__main__":
    main()
