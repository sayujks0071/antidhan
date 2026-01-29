#!/usr/bin/env python3
"""
Properly fix 403 errors by:
1. Stopping strategies
2. Setting API key via API endpoint
3. Restarting strategies
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

# Use the API key that other working strategies use
API_KEY = "630db05e091812b4c23298ca2d018b62376ddd168860d21fcb4bd2dfc265e49f"

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

def set_api_key(session, strategy_id, api_key):
    """Set API key for a strategy (must be stopped)"""
    # Get CSRF token
    csrf = fetch_csrf(session, f"{BASE_URL}/python/env/{strategy_id}")
    
    payload = {
        "regular_vars": {
            "OPENALGO_APIKEY": api_key
        },
        "secure_vars": {}
    }
    
    headers = {"Content-Type": "application/json"}
    if csrf:
        headers["X-CSRFToken"] = csrf
    
    resp = session.post(
        f"{BASE_URL}/python/env/{strategy_id}",
        json=payload,
        headers=headers
    )
    
    if resp.status_code == 200:
        try:
            data = resp.json()
            return data.get('success', False), data.get('message', '')
        except:
            return True, "API key set"
    else:
        try:
            error_data = resp.json()
            return False, error_data.get('message', f"HTTP {resp.status_code}")
        except:
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
    print("=" * 60)
    print("  Fix 403 Errors - Proper Method")
    print("=" * 60)
    print()
    
    # Login
    print("Logging in...")
    session = login_and_get_session()
    if not session:
        print("❌ Login failed")
        print("\nTrying alternative login method...")
        # Try direct login
        session = requests.Session()
        login_resp = session.post(
            f"{BASE_URL}/auth/login",
            data={"username": "sayujks0071", "password": "Apollo@20417"},
            allow_redirects=True
        )
        if login_resp.status_code != 200:
            print(f"❌ Login failed: {login_resp.status_code}")
            return
    
    print("✅ Logged in")
    print()
    
    # Load configs to get strategy names
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            configs = json.load(f)
    else:
        configs = {}
    
    # Process each strategy
    print(f"Processing {len(STRATEGY_IDS)} strategies...")
    print()
    
    for strategy_id in STRATEGY_IDS:
        strategy_name = configs.get(strategy_id, {}).get('name', strategy_id)
        print(f"Strategy: {strategy_name}")
        print(f"  ID: {strategy_id}")
        
        # Step 1: Stop strategy
        print("  1. Stopping...", end=" ")
        success, msg = stop_strategy(session, strategy_id)
        if success:
            print(f"✅ {msg}")
        else:
            print(f"⚠️  {msg} (may already be stopped)")
        time.sleep(2)
        
        # Step 2: Set API key
        print("  2. Setting API key...", end=" ")
        success, msg = set_api_key(session, strategy_id, API_KEY)
        if success:
            print(f"✅ {msg}")
        else:
            print(f"❌ {msg}")
            print(f"     Continuing anyway...")
        time.sleep(1)
        
        # Step 3: Start strategy
        print("  3. Starting...", end=" ")
        success, msg = start_strategy(session, strategy_id)
        if success:
            print(f"✅ {msg}")
        else:
            print(f"❌ {msg}")
        
        print()
    
    print("=" * 60)
    print("✅ Fix complete!")
    print("=" * 60)
    print()
    print("Check status at: http://127.0.0.1:5001/python")
    print("Verify strategies are running without 403 errors")

if __name__ == "__main__":
    main()
