#!/usr/bin/env python3
"""
Set OPENALGO_APIKEY for all strategies that don't have it.
"""
import os
import json
import re
import time
import subprocess
from pathlib import Path
from typing import Dict, Tuple
import requests

# Configuration
BASE_URL = os.environ.get("OPENALGO_BASE_URL", "http://127.0.0.1:5001").rstrip("/")

def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value

API_KEY = _require_env("OPENALGO_APIKEY")
USERNAME = _require_env("OPENALGO_USERNAME")
PASSWORD = _require_env("OPENALGO_PASSWORD")

CONFIG_PATH = Path("/Users/mac/dyad-apps/openalgo/strategies/strategy_configs.json")
ENV_PATH = Path("/Users/mac/dyad-apps/openalgo/strategies/strategy_env.json")


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


def set_api_key(session: requests.Session, strategy_id: str, api_key: str) -> Tuple[bool, str]:
    """Set API key for a strategy."""
    try:
        # Fetch CSRF token first from GET endpoint
        csrf = fetch_csrf(session, f"{BASE_URL}/python/env/{strategy_id}")
        
        payload = {
            "regular_vars": {
                "OPENALGO_APIKEY": api_key
            },
            "secure_vars": {}
        }
        
        # Set headers with CSRF token
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
                if data.get('success'):
                    return True, "API key set"
                return False, data.get('message', 'Unknown error')
            except Exception:
                return False, f"Invalid JSON response: {resp.text[:100]}"
        
        # Try to get error message
        try:
            error_data = resp.json()
            error_msg = error_data.get('message', f"HTTP {resp.status_code}")
        except Exception:
            error_msg = f"HTTP {resp.status_code}: {resp.text[:100]}"
        
        return False, error_msg
    except Exception as e:
        return False, str(e)


def main():
    """Main function."""
    print("=" * 80)
    print("SET API KEYS FOR ALL STRATEGIES")
    print("=" * 80)
    
    # Load configs
    if not CONFIG_PATH.exists():
        print("❌ Strategy configs not found")
        return
    
    configs = json.loads(CONFIG_PATH.read_text())
    
    # Load existing env data
    env_data = {}
    if ENV_PATH.exists():
        env_data = json.loads(ENV_PATH.read_text())
    
    # Find strategies without API keys
    needs_api_key = []
    for strategy_id, config in configs.items():
        has_key = strategy_id in env_data and 'OPENALGO_APIKEY' in env_data[strategy_id]
        if not has_key:
            needs_api_key.append((strategy_id, config.get('name', strategy_id)))
    
    if not needs_api_key:
        print("\n✅ All strategies already have API keys!")
        return
    
    print(f"\nFound {len(needs_api_key)} strategies without API keys:")
    for sid, name in needs_api_key:
        print(f"  - {name} ({sid})")
    
    # Login
    session = requests.Session()
    print("\n1. Logging in...")
    if not login(session):
        print("❌ Login failed")
        return
    print("✅ Logged in")
    
    # Set API keys
    print("\n2. Setting API keys...")
    for idx, (strategy_id, name) in enumerate(needs_api_key):
        print(f"\nProcessing: {name} ({strategy_id}) [{idx+1}/{len(needs_api_key)}]")
        
        # Re-login every 3 strategies to prevent session expiration
        if idx > 0 and idx % 3 == 0:
            print("  Refreshing session...")
            if not login(session):
                print("  ❌ Re-login failed, aborting")
                break
        
        # Check if running
        config = configs.get(strategy_id, {})
        was_running = config.get('is_running', False) and check_process_status(config.get('pid'))
        
        # Stop if running
        if was_running:
            print("  Stopping...")
            success, msg = stop_strategy(session, strategy_id)
            if success:
                print("  ✅ Stopped")
            else:
                print(f"  ⚠️  Stop failed: {msg}")
                # Try re-login and retry once
                if "session" in msg.lower() or "expired" in msg.lower():
                    print("  Re-logging in...")
                    if login(session):
                        success, msg = stop_strategy(session, strategy_id)
                        if success:
                            print("  ✅ Stopped (after re-login)")
                        else:
                            print(f"  ⚠️  Stop failed again: {msg}")
                            continue
                    else:
                        continue
                else:
                    continue
        
        # Set API key
        print("  Setting API key...")
        success, msg = set_api_key(session, strategy_id, API_KEY)
        if success:
            print("  ✅ API key set")
        else:
            # Try re-login and retry once
            if "session" in msg.lower() or "expired" in msg.lower() or "csrf" in msg.lower():
                print(f"  ⚠️  {msg}, re-logging in...")
                if login(session):
                    success, msg = set_api_key(session, strategy_id, API_KEY)
                    if success:
                        print("  ✅ API key set (after re-login)")
                    else:
                        print(f"  ⚠️  Failed again: {msg}")
                        continue
                else:
                    continue
            else:
                print(f"  ⚠️  Failed: {msg}")
                continue
        
        # Restart if was running
        if was_running:
            print("  Restarting...")
            time.sleep(1)
            success, msg = start_strategy(session, strategy_id)
            if success:
                print("  ✅ Restarted")
            else:
                print(f"  ⚠️  Restart failed: {msg}")
        
        # Small delay between strategies
        time.sleep(2)
    
    print("\n" + "=" * 80)
    print("✅ API key setup complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
