#!/usr/bin/env python3
"""
Start Live Trading Script
Starts one or more strategies for live trading via the OpenAlgo API
Requires authentication via web UI first, or provides instructions
"""

import requests
import json
import sys
import re
from pathlib import Path

# Configuration
BASE_URL = "http://127.0.0.1:5001"
STRATEGIES_CONFIG = Path(__file__).parent.parent / "strategies" / "strategy_configs.json"

def extract_csrf_token(html_content):
    """Extract CSRF token from HTML"""
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html_content)
    if match:
        return match.group(1)
    # Alternative pattern
    match = re.search(r'csrf_token["\']?\s*[:=]\s*["\']([^"\']+)["\']', html_content)
    return match.group(1) if match else None

def get_strategies():
    """Load available strategies"""
    if not STRATEGIES_CONFIG.exists():
        print("❌ Strategy configs file not found")
        return {}
    
    with open(STRATEGIES_CONFIG, 'r') as f:
        return json.load(f)

def check_server():
    """Check if server is running"""
    try:
        resp = requests.get(f"{BASE_URL}/api/v1/ping", timeout=3)
        return True
    except:
        return False

def login_and_get_session(username=None, password=None):
    """Login to OpenAlgo and return session"""
    session = requests.Session()
    
    # Get CSRF token
    try:
        login_page = session.get(f"{BASE_URL}/auth/login", timeout=5)
        csrf_token = extract_csrf_token(login_page.text)
        
        if not username or not password:
            return None, "Username and password required for API login"
        
        # Login
        login_data = {
            "username": username,
            "password": password
        }
        if csrf_token:
            login_data["csrf_token"] = csrf_token
        
        login_resp = session.post(f"{BASE_URL}/auth/login", data=login_data, allow_redirects=True)
        
        # Check if login successful
        if '/auth/broker' in login_resp.url or '/dashboard' in login_resp.url:
            return session, None
        else:
            return None, "Login failed - check credentials"
    except Exception as e:
        return None, f"Login error: {str(e)}"

def start_strategy_api(session, strategy_id):
    """Start a strategy via API"""
    try:
        resp = session.post(f"{BASE_URL}/python/start/{strategy_id}", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('success', False), data.get('message', 'Unknown response')
        else:
            return False, f"HTTP {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        return False, f"Error: {str(e)}"

def main():
    print("=" * 60)
    print("  START LIVE TRADING")
    print("=" * 60)
    print()
    
    # Check server
    if not check_server():
        print("❌ Server is not running!")
        print(f"   Start server first: cd {Path(__file__).parent.parent} && ./QUICK_START.sh")
        sys.exit(1)
    
    print("✅ Server is running")
    print()
    
    # Get strategies
    strategies = get_strategies()
    if not strategies:
        print("❌ No strategies found")
        sys.exit(1)
    
    # Filter stopped strategies
    stopped = {sid: config for sid, config in strategies.items() 
               if not config.get('is_running', False)}
    
    if not stopped:
        print("✅ All strategies are already running!")
        sys.exit(0)
    
    print(f"📦 Found {len(stopped)} stopped strategies:")
    print()
    
    for i, (sid, config) in enumerate(sorted(stopped.items()), 1):
        print(f"  {i:2d}. {config.get('name', sid)}")
    
    print()
    print("=" * 60)
    print("  STARTING STRATEGIES")
    print("=" * 60)
    print()
    print("⚠️  IMPORTANT: Starting strategies requires authentication.")
    print()
    print("Option 1: Use Web UI (Easiest)")
    print(f"  1. Open: {BASE_URL}/python/")
    print("  2. Login if required")
    print("  3. Click 'Start' button for each strategy")
    print()
    print("Option 2: Use this script with credentials")
    print("  Set environment variables:")
    print("    export OPENALGO_USERNAME=your_username")
    print("    export OPENALGO_PASSWORD=your_password")
    print("  Then run: python3 scripts/start_live_trading.py --all")
    print()
    
    # Check if --all flag and credentials provided
    if '--all' in sys.argv:
        import os
        username = os.getenv('OPENALGO_USERNAME')
        password = os.getenv('OPENALGO_PASSWORD')
        
        if not username or not password:
            print("❌ Credentials not provided!")
            print("   Set OPENALGO_USERNAME and OPENALGO_PASSWORD environment variables")
            sys.exit(1)
        
        # Login
        print("🔐 Authenticating...")
        session, error = login_and_get_session(username, password)
        if not session:
            print(f"❌ {error}")
            sys.exit(1)
        
        print("✅ Authenticated")
        print()
        
        # Start all strategies
        print("🚀 Starting strategies...")
        print()
        success_count = 0
        failed = []
        
        for sid, config in sorted(stopped.items()):
            name = config.get('name', sid)
            print(f"  Starting: {name}...", end=" ")
            success, message = start_strategy_api(session, sid)
            if success:
                print("✅")
                success_count += 1
            else:
                print(f"❌ {message}")
                failed.append((name, message))
        
        print()
        print("=" * 60)
        print(f"  RESULTS: {success_count}/{len(stopped)} started successfully")
        print("=" * 60)
        
        if failed:
            print("\n⚠️  Failed strategies:")
            for name, msg in failed:
                print(f"  - {name}: {msg}")
        
        print(f"\n📊 Monitor at: {BASE_URL}/dashboard")
        print(f"📋 Manage at: {BASE_URL}/python/")
    else:
        # Show instructions
        print("=" * 60)
        print("  STRATEGY DETAILS")
        print("=" * 60)
        print()
        for sid, config in sorted(stopped.items()):
            print(f"  📋 {config.get('name', sid)}")
            print(f"     ID: {sid}")
            print(f"     Start URL: {BASE_URL}/python/")
            print()

if __name__ == "__main__":
    main()
