#!/usr/bin/env python3
"""
Test login functionality
"""

import sys
import os
import re

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

import requests

def test_login():
    """Test login via HTTP"""
    session = requests.Session()
    
    # Get login page
    print("1. Fetching login page...")
    login_page = session.get('http://127.0.0.1:5002/auth/login')
    print(f"   Status: {login_page.status_code}")
    
    if login_page.status_code != 200:
        print(f"   ❌ Failed to load login page")
        return False
    
    # Extract CSRF token
    print("2. Extracting CSRF token...")
    csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', login_page.text)
    if not csrf_match:
        print("   ❌ CSRF token not found")
        return False
    
    csrf_token = csrf_match.group(1)
    print(f"   ✅ CSRF token found: {csrf_token[:20]}...")
    
    # Try login
    print("3. Attempting login...")
    login_data = {
        'username': 'sayujks0071',
        'password': 'Apollo@20417',
        'csrf_token': csrf_token
    }
    
    response = session.post('http://127.0.0.1:5002/auth/login', data=login_data)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text[:200]}")
    
    if response.status_code == 200:
        try:
            data = response.json()
            if data.get('status') == 'success':
                print("   ✅ Login successful!")
                return True
            else:
                print(f"   ❌ Login failed: {data.get('message', 'Unknown error')}")
                return False
        except:
            print("   ⚠️  Response is not JSON")
            return False
    else:
        print(f"   ❌ Login failed with status {response.status_code}")
        return False

if __name__ == "__main__":
    success = test_login()
    sys.exit(0 if success else 1)
