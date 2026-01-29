#!/usr/bin/env python3
"""Start MCX strategies that are not currently running"""
import requests
import json
import re
from pathlib import Path

BASE_URL = "http://127.0.0.1:5001"
USERNAME = "sayujks0071"
PASSWORD = "Apollo@20417"

def main():
    session = requests.Session()
    
    # Get CSRF token from login page
    print("Getting CSRF token...")
    login_page = session.get(f"{BASE_URL}/auth/login")
    csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', login_page.text)
    csrf_token = csrf_match.group(1) if csrf_match else None
    
    if not csrf_token:
        print("Could not find CSRF token")
        return
    
    # Login
    print("Logging in...")
    login_resp = session.post(f"{BASE_URL}/auth/login", data={
        "username": USERNAME,
        "password": PASSWORD,
        "csrf_token": csrf_token
    }, allow_redirects=False)
    
    if login_resp.status_code not in (200, 302):
        print(f"Login failed: {login_resp.status_code}")
        return
    
    print("Login successful!")
    
    # Read strategy configs
    config_path = Path(__file__).parent.parent / "strategies" / "strategy_configs.json"
    with open(config_path) as f:
        configs = json.load(f)
    
    # Find MCX strategies that are not running
    mcx_strategies_to_start = []
    for strategy_id, config in configs.items():
        if "mcx" in strategy_id.lower() and not config.get("is_running", False):
            mcx_strategies_to_start.append((strategy_id, config.get("name", strategy_id)))
    
    if not mcx_strategies_to_start:
        print("All MCX strategies are already running!")
        return
    
    print(f"\nFound {len(mcx_strategies_to_start)} MCX strategies to start:")
    for strategy_id, name in mcx_strategies_to_start:
        print(f"  - {name} ({strategy_id})")
    
    # Get CSRF token from python page
    print("\nGetting CSRF token for strategy endpoints...")
    python_page = session.get(f"{BASE_URL}/python/")
    csrf_match = re.search(r'name="csrf_token" content="([^"]+)"', python_page.text)
    if not csrf_match:
        csrf_match = re.search(r'csrf-token" content="([^"]+)"', python_page.text)
    csrf_token = csrf_match.group(1) if csrf_match else None
    
    if not csrf_token:
        print("Warning: Could not find CSRF token, trying without it...")
    
    # Start each strategy
    print("\nStarting strategies...")
    for strategy_id, name in mcx_strategies_to_start:
        print(f"\nStarting {name}...")
        headers = {}
        if csrf_token:
            headers["X-CSRFToken"] = csrf_token
        
        start_resp = session.post(
            f"{BASE_URL}/python/start/{strategy_id}",
            headers=headers,
            allow_redirects=False
        )
        
        if start_resp.status_code == 200:
            try:
                data = start_resp.json()
                if data.get("success"):
                    print(f"  ✓ Successfully started: {data.get('message', 'Started')}")
                else:
                    print(f"  ✗ Failed: {data.get('message', 'Unknown error')}")
            except Exception as e:
                print(f"  ✗ Error parsing response: {e}")
                print(f"  Response text: {start_resp.text[:200]}")
        else:
            print(f"  ✗ HTTP {start_resp.status_code}")
            if start_resp.text:
                print(f"  Response: {start_resp.text[:200]}")
    
    print("\nDone!")

if __name__ == "__main__":
    main()
