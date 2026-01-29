#!/usr/bin/env python3
"""Deploy top NIFTY strategies directly."""
import os
import re
import time
import requests
from pathlib import Path

BASE_URL = os.environ.get("OPENALGO_BASE_URL", "http://127.0.0.1:5001").rstrip("/")

def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value

USERNAME = _require_env("OPENALGO_USERNAME")
PASSWORD = _require_env("OPENALGO_PASSWORD")

STRATEGIES = [
    ("NIFTY Greeks Enhanced", "strategies/scripts/nifty_greeks_enhanced_20260122.py"),
    ("NIFTY Multi-Strike Momentum", "strategies/scripts/nifty_multistrike_momentum_20260122.py"),
]

def extract_csrf(html):
    # Try multiple patterns
    patterns = [
        r'name="csrf_token" value="([^"]+)"',
        r'csrf_token["\']?\s*[:=]\s*["\']([^"\']+)',
        r'<input[^>]*name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

def login(session):
    """Login and return CSRF token."""
    resp = session.get(f"{BASE_URL}/auth/login", allow_redirects=True)
    csrf = extract_csrf(resp.text)
    if not csrf:
        print("⚠️  Could not extract CSRF token")
        return False
    payload = {"username": USERNAME, "password": PASSWORD, "csrf_token": csrf}
    resp = session.post(f"{BASE_URL}/auth/login", data=payload, allow_redirects=True)
    
    # Check if we're redirected away from login (success)
    if '/auth/broker' in resp.url or '/dashboard' in resp.url:
        return True
    
    # Check JSON response
    try:
        data = resp.json()
        if data.get("status") == "success":
            return True
    except:
        pass
    
    # If we're not on login page, assume success
    if '/auth/login' not in resp.url:
        return True
    
    print(f"Login may have failed. Final URL: {resp.url}")
    return False

def upload_strategy(session, name, file_path):
    """Upload a strategy."""
    base_dir = Path("/Users/mac/dyad-apps/openalgo")
    full_path = base_dir / file_path
    
    if not full_path.exists():
        print(f"❌ File not found: {full_path}")
        return False
    
    # Get CSRF token
    resp = session.get(f"{BASE_URL}/python/new")
    csrf = extract_csrf(resp.text)
    
    # Upload
    with open(full_path, 'rb') as f:
        files = {"strategy_file": (full_path.name, f, "text/x-python")}
        data = {"strategy_name": name}
        if csrf:
            data["csrf_token"] = csrf
        resp = session.post(f"{BASE_URL}/python/new", data=data, files=files, allow_redirects=True)
    
    if resp.status_code in (200, 302):
        print(f"✅ Uploaded: {name}")
        time.sleep(1)  # Allow server to process
        return True
    else:
        print(f"❌ Upload failed for {name}: {resp.status_code}")
        return False

def main():
    session = requests.Session()
    
    print("Logging in...")
    if not login(session):
        print("❌ Login failed")
        return
    
    print("✅ Logged in")
    print()
    
    for name, file_path in STRATEGIES:
        print(f"Uploading {name}...")
        upload_strategy(session, name, file_path)
        time.sleep(2)  # Rate limit protection
    
    print()
    print("✅ Deployment complete!")
    print("Next: Start strategies via web UI at http://127.0.0.1:5001/python/")

if __name__ == "__main__":
    main()
