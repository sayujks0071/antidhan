#!/usr/bin/env python3
"""
Login to Kite via OpenAlgo and Start MCX Strategies
Uses the browser-strategy-config subagent workflow
"""
import requests
import re
import time
import json
from pathlib import Path

BASE_URL = "http://127.0.0.1:5001"
USERNAME = "sayujks0071"
PASSWORD = "Apollo@20417"

def login_to_openalgo():
    """Login to OpenAlgo and return session"""
    session = requests.Session()
    
    print("=" * 60)
    print("  LOGGING INTO OPENALGO (Port 5001)")
    print("=" * 60)
    print()
    
    # Get login page
    print("1. Getting login page...")
    try:
        response = session.get(f"{BASE_URL}/auth/login")
        if response.status_code != 200:
            print(f"   ❌ Failed to get login page: {response.status_code}")
            return None
        
        print("   ✅ Login page accessible")
        
        # Extract CSRF token
        csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
        if csrf_match:
            csrf_token = csrf_match.group(1)
            print(f"   ✅ CSRF token found")
        else:
            csrf_token = None
            print("   ⚠️  CSRF token not found")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None
    
    # Login
    print()
    print("2. Attempting login...")
    login_data = {
        "username": USERNAME,
        "password": PASSWORD
    }
    
    if csrf_token:
        login_data["csrf_token"] = csrf_token
    
    try:
        response = session.post(f"{BASE_URL}/auth/login", data=login_data, allow_redirects=False)
        
        if response.status_code == 200:
            try:
                data = response.json()
                if data.get('status') == 'success':
                    print("   ✅ Login successful!")
                    return session
                else:
                    print(f"   ⚠️  Login failed: {data.get('message', 'Unknown error')}")
                    return None
            except:
                # Check if redirected to dashboard
                if 'dashboard' in response.text.lower() or 'broker' in response.text.lower():
                    print("   ✅ Login successful!")
                    return session
                else:
                    print(f"   ⚠️  Unexpected response: {response.text[:200]}")
                    return None
        elif response.status_code == 302:
            print("   ✅ Login successful (redirected)")
            # Follow redirect
            redirect_url = response.headers.get('Location', '')
            if redirect_url:
                session.get(f"{BASE_URL}{redirect_url}")
            return session
        elif response.status_code == 429:
            print("   ❌ Rate limit exceeded - wait 1-2 minutes")
            return None
        else:
            print(f"   ⚠️  Status: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return None
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None

def connect_kite_broker(session):
    """Connect to Kite broker via OpenAlgo"""
    print()
    print("=" * 60)
    print("  CONNECTING TO KITE BROKER")
    print("=" * 60)
    print()
    
    # Check broker status
    print("1. Checking broker status...")
    try:
        response = session.get(f"{BASE_URL}/auth/broker")
        if response.status_code == 200:
            print("   ✅ Broker page accessible")
            
            # Check if already connected
            if 'zerodha' in response.text.lower() and 'connected' in response.text.lower():
                print("   ✅ Kite/Zerodha already connected!")
                return True
            
            # Get Kite login URL
            kite_match = re.search(r'href="([^"]*zerodha[^"]*login[^"]*)"', response.text, re.IGNORECASE)
            if kite_match:
                kite_url = kite_match.group(1)
                if not kite_url.startswith('http'):
                    kite_url = f"{BASE_URL}{kite_url}"
                print(f"   Found Kite login URL: {kite_url}")
                print()
                print("   ⚠️  Manual step required:")
                print(f"   1. Open browser: {kite_url}")
                print("   2. Complete Kite OAuth login")
                print("   3. You'll be redirected back to OpenAlgo")
                print()
                return False
            else:
                print("   ⚠️  Kite login URL not found in page")
                print("   You may need to login manually via browser")
                return False
        else:
            print(f"   ❌ Failed to access broker page: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def start_mcx_strategies(session):
    """Start MCX strategies"""
    print()
    print("=" * 60)
    print("  STARTING MCX STRATEGIES")
    print("=" * 60)
    print()
    
    # Navigate to strategy page
    print("1. Getting strategy list...")
    try:
        response = session.get(f"{BASE_URL}/python")
        if response.status_code != 200:
            print(f"   ❌ Failed to get strategy page: {response.status_code}")
            return False
        
        print("   ✅ Strategy page accessible")
        
        # Find MCX strategies
        mcx_strategies = []
        # Look for MCX strategy names in the page
        mcx_patterns = [
            r'mcx_global_arbitrage',
            r'mcx_commodity_momentum',
            r'mcx_advanced',
            r'mcx_elite',
            r'mcx_neural'
        ]
        
        for pattern in mcx_patterns:
            matches = re.findall(pattern, response.text, re.IGNORECASE)
            if matches:
                mcx_strategies.extend(matches)
        
        if not mcx_strategies:
            print("   ⚠️  No MCX strategies found in page")
            print("   Strategy page loaded, but no MCX strategies detected")
            print("   You may need to start them manually via Web UI")
            return False
        
        print(f"   Found {len(set(mcx_strategies))} MCX strategy patterns")
        print()
        print("   ⚠️  Starting strategies requires browser automation")
        print("   Use the browser-strategy-config subagent to start strategies")
        print("   Or start manually via: http://127.0.0.1:5001/python")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def main():
    print()
    print("=" * 60)
    print("  KITE LOGIN & MCX STRATEGY STARTUP")
    print("=" * 60)
    print()
    
    # Step 1: Login to OpenAlgo
    session = login_to_openalgo()
    if not session:
        print()
        print("❌ Failed to login to OpenAlgo")
        print("   Please check:")
        print("   1. Server is running on port 5001")
        print("   2. Credentials are correct")
        print("   3. Rate limit has cleared (wait 1-2 minutes if needed)")
        return
    
    # Step 2: Connect Kite broker
    kite_connected = connect_kite_broker(session)
    
    # Step 3: Start MCX strategies
    strategies_ready = start_mcx_strategies(session)
    
    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print()
    print(f"✅ OpenAlgo Login: Success")
    print(f"{'✅' if kite_connected else '⚠️ '} Kite Broker: {'Connected' if kite_connected else 'Manual login required'}")
    print(f"{'✅' if strategies_ready else '⚠️ '} MCX Strategies: {'Ready' if strategies_ready else 'Use browser to start'}")
    print()
    print("📋 Next Steps:")
    if not kite_connected:
        print("   1. Connect Kite broker via browser: http://127.0.0.1:5001/auth/broker")
    print("   2. Start MCX strategies via: http://127.0.0.1:5001/python")
    print("   3. Monitor status using MCP tools in Cursor")
    print()

if __name__ == "__main__":
    main()
