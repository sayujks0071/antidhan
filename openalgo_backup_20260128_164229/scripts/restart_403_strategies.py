#!/usr/bin/env python3
"""
Restart strategies that had 403 errors after setting API keys
"""
import json
import requests
import time
import re
from pathlib import Path

BASE_URL = "http://127.0.0.1:5001"
CONFIG_FILE = Path(__file__).parent.parent / "strategies" / "strategy_configs.json"

# Strategy IDs that had 403 errors
STRATEGY_IDS = [
    "mcx_global_arbitrage_strategy_20260128110030",
    "natural_gas_clawdbot_strategy_20260128110030",
    "crude_oil_enhanced_strategy_20260128110030"
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
    
    if '/auth/broker' in login_resp.url or '/dashboard' in login_resp.url:
        return session
    return None

def restart_strategy(session, strategy_id):
    """Restart a strategy"""
    # Stop if running
    stop_resp = session.post(f"{BASE_URL}/python/stop/{strategy_id}")
    time.sleep(2)
    
    # Start
    start_resp = session.post(f"{BASE_URL}/python/start/{strategy_id}")
    
    if start_resp.status_code == 200:
        try:
            data = start_resp.json()
            if data.get('success'):
                return True, "Started successfully"
            return False, data.get('message', 'Unknown error')
        except:
            if start_resp.status_code == 200:
                return True, "Started (no JSON response)"
    return False, f"HTTP {start_resp.status_code}"

def main():
    print("=" * 60)
    print("  Restart Strategies with API Keys")
    print("=" * 60)
    print()
    
    # Login
    print("Logging in...")
    session = login_and_get_session()
    if not session:
        print("❌ Login failed")
        return
    
    print("✅ Logged in")
    print()
    
    # Load configs to get strategy names
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            configs = json.load(f)
    else:
        configs = {}
    
    # Restart each strategy
    print("Restarting strategies...")
    print()
    
    for strategy_id in STRATEGY_IDS:
        strategy_name = configs.get(strategy_id, {}).get('name', strategy_id)
        print(f"Restarting: {strategy_name}...", end=" ")
        
        success, message = restart_strategy(session, strategy_id)
        if success:
            print(f"✅ {message}")
        else:
            print(f"❌ {message}")
    
    print()
    print("=" * 60)
    print("✅ Restart complete!")
    print("=" * 60)
    print()
    print("Check status at: http://127.0.0.1:5001/python")

if __name__ == "__main__":
    main()
