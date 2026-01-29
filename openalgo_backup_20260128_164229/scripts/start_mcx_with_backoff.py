#!/usr/bin/env python3
"""
Start MCX strategies with rate limit handling and exponential backoff
"""
import requests
import json
import re
import time
from pathlib import Path

BASE_URL = "http://127.0.0.1:5001"
USERNAME = "sayujks0071"
PASSWORD = "Apollo@20417"

def login_with_retry(max_retries=3):
    """Login with retry logic for rate limits"""
    session = requests.Session()
    
    for attempt in range(max_retries):
        try:
            print(f"Login attempt {attempt + 1}/{max_retries}...")
            
            # Get login page with delay
            time.sleep(2 ** attempt)  # Exponential backoff
            login_page = session.get(f"{BASE_URL}/auth/login", timeout=10)
            
            if login_page.status_code == 429:
                wait_time = 60 * (attempt + 1)
                print(f"   Rate limited. Waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            
            csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', login_page.text)
            csrf_token = csrf_match.group(1) if csrf_match else None
            
            if not csrf_token:
                print("   ⚠️  CSRF token not found, retrying...")
                continue
            
            # Login with delay
            time.sleep(1)
            login_resp = session.post(f"{BASE_URL}/auth/login", data={
                "username": USERNAME,
                "password": PASSWORD,
                "csrf_token": csrf_token
            }, allow_redirects=False, timeout=10)
            
            if login_resp.status_code == 429:
                wait_time = 60 * (attempt + 1)
                print(f"   Rate limited. Waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            
            if login_resp.status_code in (200, 302):
                print("   ✅ Login successful!")
                return session
            else:
                print(f"   ⚠️  Status: {login_resp.status_code}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            if attempt < max_retries - 1:
                wait_time = 30 * (attempt + 1)
                print(f"   Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
    
    return None

def start_strategies_with_backoff(session):
    """Start MCX strategies with rate limit handling"""
    config_path = Path(__file__).parent.parent / "strategies" / "strategy_configs.json"
    
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        return
    
    with open(config_path) as f:
        configs = json.load(f)
    
    # Find MCX strategies
    mcx_strategies = []
    for strategy_id, config in configs.items():
        if "mcx" in strategy_id.lower() and not config.get("is_running", False):
            mcx_strategies.append((strategy_id, config.get("name", strategy_id)))
    
    if not mcx_strategies:
        print("✅ All MCX strategies are already running!")
        return
    
    print(f"\nFound {len(mcx_strategies)} MCX strategies to start:")
    for strategy_id, name in mcx_strategies:
        print(f"  - {name} ({strategy_id})")
    
    # Get CSRF token with retry
    print("\nGetting CSRF token...")
    csrf_token = None
    for attempt in range(3):
        try:
            time.sleep(2 ** attempt)  # Exponential backoff
            python_page = session.get(f"{BASE_URL}/python/", timeout=10)
            
            if python_page.status_code == 429:
                wait_time = 60
                print(f"   Rate limited. Waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            
            csrf_match = re.search(r'name="csrf_token" content="([^"]+)"', python_page.text)
            if not csrf_match:
                csrf_match = re.search(r'csrf-token" content="([^"]+)"', python_page.text)
            csrf_token = csrf_match.group(1) if csrf_match else None
            
            if csrf_token:
                print("   ✅ CSRF token found")
                break
        except Exception as e:
            print(f"   ⚠️  Attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(30)
    
    # Start strategies with delays
    print("\nStarting strategies (with 5s delay between each)...")
    headers = {}
    if csrf_token:
        headers["X-CSRFToken"] = csrf_token
    
    success_count = 0
    for i, (strategy_id, name) in enumerate(mcx_strategies, 1):
        print(f"\n[{i}/{len(mcx_strategies)}] Starting {name}...")
        
        # Delay between requests
        if i > 1:
            delay = 5
            print(f"   Waiting {delay}s to avoid rate limits...")
            time.sleep(delay)
        
        try:
            start_resp = session.post(
                f"{BASE_URL}/python/start/{strategy_id}",
                headers=headers,
                allow_redirects=False,
                timeout=10
            )
            
            if start_resp.status_code == 429:
                print(f"   ⚠️  Rate limited. Waiting 60s...")
                time.sleep(60)
                # Retry once
                start_resp = session.post(
                    f"{BASE_URL}/python/start/{strategy_id}",
                    headers=headers,
                    allow_redirects=False,
                    timeout=10
                )
            
            if start_resp.status_code == 200:
                try:
                    data = start_resp.json()
                    if data.get("success"):
                        print(f"   ✅ Started: {data.get('message', 'Started')}")
                        success_count += 1
                    else:
                        msg = data.get('message', 'Unknown error')
                        print(f"   ⚠️  {msg}")
                        if "broker session" in msg.lower():
                            print("      → Kite broker needs to be connected first!")
                except:
                    print(f"   ⚠️  Response: {start_resp.text[:100]}")
            else:
                print(f"   ❌ HTTP {start_resp.status_code}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print(f"\n✅ Started {success_count}/{len(mcx_strategies)} strategies successfully")
    if success_count < len(mcx_strategies):
        print("\n⚠️  Some strategies failed. Common reasons:")
        print("   - Kite broker not connected (connect at http://127.0.0.1:5001/auth/broker)")
        print("   - Rate limiting (wait 1-2 minutes and try again)")
        print("   - Strategy configuration issues")

def main():
    print("=" * 60)
    print("  START MCX STRATEGIES (WITH RATE LIMIT HANDLING)")
    print("=" * 60)
    print()
    
    session = login_with_retry()
    if not session:
        print("\n❌ Failed to login after retries")
        print("   Please wait 1-2 minutes and try again")
        return
    
    start_strategies_with_backoff(session)
    
    print("\n" + "=" * 60)
    print("  DONE")
    print("=" * 60)

if __name__ == "__main__":
    main()
