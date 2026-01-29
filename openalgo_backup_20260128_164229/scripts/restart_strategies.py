#!/usr/bin/env python3
"""
Restart specific strategies.
Usage: python restart_strategies.py --strategies orb_strategy trend_pullback_strategy
"""
import os
import sys
import re
import time
import subprocess
from pathlib import Path
from typing import List, Tuple
import requests

# Configuration
BASE_URL = os.environ.get("OPENALGO_BASE_URL", "http://127.0.0.1:5001").rstrip("/")

def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value

USERNAME = _require_env("OPENALGO_USERNAME")
PASSWORD = _require_env("OPENALGO_PASSWORD")


def extract_csrf_token(html: str):
    """Extract CSRF token from HTML."""
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return match.group(1) if match else None


def fetch_csrf(session: requests.Session, url: str):
    """Fetch CSRF token from a URL."""
    resp = session.get(url, allow_redirects=True)
    if not resp.ok:
        return None
    return extract_csrf_token(resp.text)


def login(session: requests.Session) -> bool:
    """Login to OpenAlgo."""
    for attempt in range(3):
        login_csrf = fetch_csrf(session, f"{BASE_URL}/auth/login")
        login_payload = {"username": USERNAME, "password": PASSWORD}
        if login_csrf:
            login_payload["csrf_token"] = login_csrf
        
        login_resp = session.post(f"{BASE_URL}/auth/login", data=login_payload, allow_redirects=True)
        
        try:
            login_data = login_resp.json()
            if login_data.get("status") == "success":
                return True
        except Exception:
            if '/auth/broker' in login_resp.url or '/dashboard' in login_resp.url:
                return True
        
        if login_resp.status_code == 429:
            wait_s = 65
            print(f"Rate limited. Waiting {wait_s}s...")
            time.sleep(wait_s)
            continue
    
    return False


def check_process_status(pid):
    """Check if process is running."""
    if not pid:
        return False
    try:
        result = subprocess.run(['ps', '-p', str(pid)], capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False


def stop_strategy(session: requests.Session, strategy_id: str) -> Tuple[bool, str]:
    """Stop a strategy."""
    try:
        resp = session.post(f"{BASE_URL}/python/stop/{strategy_id}")
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                # Wait for process termination
                time.sleep(2)
                return True, "Stopped"
            return False, data.get('message', 'Unknown error')
        return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)


def start_strategy(session: requests.Session, strategy_id: str) -> Tuple[bool, str]:
    """Start a strategy."""
    try:
        resp = session.post(f"{BASE_URL}/python/start/{strategy_id}")
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                time.sleep(1)
                return True, "Started"
            return False, data.get('message', 'Unknown error')
        return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)


def restart_strategy(session: requests.Session, strategy_id: str) -> Tuple[bool, str]:
    """Restart a strategy."""
    print(f"  Stopping {strategy_id}...")
    success, msg = stop_strategy(session, strategy_id)
    if not success:
        return False, f"Stop failed: {msg}"
    
    print(f"  Starting {strategy_id}...")
    success, msg = start_strategy(session, strategy_id)
    if not success:
        return False, f"Start failed: {msg}"
    
    return True, "Restarted successfully"


def main():
    """Main function."""
    # Parse command line arguments
    if '--strategies' in sys.argv:
        idx = sys.argv.index('--strategies')
        strategy_ids = sys.argv[idx + 1:]
    else:
        # Default: restart strategies with bug fixes
        strategy_ids = ['orb_strategy', 'trend_pullback_strategy']
    
    if not strategy_ids:
        print("Usage: python restart_strategies.py --strategies <strategy_id1> <strategy_id2> ...")
        print("Or run without arguments to restart default strategies (ORB, Trend Pullback)")
        return
    
    print("=" * 80)
    print("RESTART STRATEGIES")
    print("=" * 80)
    print(f"Strategies to restart: {', '.join(strategy_ids)}")
    
    # Login
    session = requests.Session()
    print("\n1. Logging in...")
    if not login(session):
        print("❌ Login failed")
        return
    print("✅ Logged in")
    
    # Restart each strategy
    print("\n2. Restarting strategies...")
    for strategy_id in strategy_ids:
        print(f"\nProcessing: {strategy_id}")
        success, msg = restart_strategy(session, strategy_id)
        if success:
            print(f"  ✅ {msg}")
        else:
            print(f"  ❌ Failed: {msg}")
    
    print("\n" + "=" * 80)
    print("✅ Restart complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
