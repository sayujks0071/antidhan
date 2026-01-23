#!/usr/bin/env python3
"""
Comprehensive strategy management script.
Handles login, status checking, API key setup, and strategy restarts.
"""
import os
import json
import re
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional
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

# Strategies that need restart due to bug fixes
STRATEGIES_NEEDING_RESTART = {
    "orb_strategy",
    "trend_pullback_strategy"
}


def extract_csrf_token(html: str) -> Optional[str]:
    """Extract CSRF token from HTML."""
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return match.group(1) if match else None


def fetch_csrf(session: requests.Session, url: str) -> Optional[str]:
    """Fetch CSRF token from a URL."""
    resp = session.get(url, allow_redirects=True)
    if not resp.ok:
        return None
    return extract_csrf_token(resp.text)


def login_to_openalgo(session: requests.Session) -> bool:
    """Login to OpenAlgo API with CSRF handling and rate limit retry."""
    for attempt in range(3):
        login_csrf = fetch_csrf(session, f"{BASE_URL}/auth/login")
        login_payload = {"username": USERNAME, "password": PASSWORD}
        if login_csrf:
            login_payload["csrf_token"] = login_csrf
        
        login_resp = session.post(f"{BASE_URL}/auth/login", data=login_payload, allow_redirects=True)
        
        try:
            login_data = login_resp.json()
        except Exception:
            # Check if redirected (success)
            if '/auth/broker' in login_resp.url or '/dashboard' in login_resp.url:
                return True
            login_data = {}
        
        if login_data.get("error") == "Rate limit exceeded":
            wait_s = 65
            print(f"Login rate limited. Waiting {wait_s}s before retry...")
            time.sleep(wait_s)
            continue
        
        if login_data.get("status") == "success":
            return True
        
        # Check redirect (also success)
        if '/auth/broker' in login_resp.url or '/dashboard' in login_resp.url:
            return True
    
    return False


def get_all_strategies(session: requests.Session) -> Dict[str, Dict]:
    """Get all strategies from API or config file."""
    # Try API endpoint first
    try:
        status_resp = session.get(f"{BASE_URL}/python/status")
        if status_resp.status_code == 200:
            try:
                status_data = status_resp.json()
                if isinstance(status_data, dict) and 'strategies' in status_data:
                    return status_data['strategies']
            except Exception:
                pass
    except Exception:
        pass
    
    # Fallback to config file
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    
    return {}


def check_process_status(pid: Optional[int]) -> bool:
    """Check if a process is running."""
    if not pid:
        return False
    try:
        result = subprocess.run(['ps', '-p', str(pid)], capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False


def check_strategy_status(strategy_id: str, config: Dict, env_data: Dict) -> Dict:
    """Check strategy status: running, has API key, needs restart."""
    is_running = config.get('is_running', False)
    pid = config.get('pid')
    
    # Verify process is actually running
    if is_running and pid:
        is_running = check_process_status(pid)
    
    # Check API key
    has_api_key = strategy_id in env_data and 'OPENALGO_APIKEY' in env_data[strategy_id]
    
    # Check if needs restart (bug fixes)
    needs_restart = strategy_id in STRATEGIES_NEEDING_RESTART
    
    return {
        'is_running': is_running,
        'pid': pid,
        'has_api_key': has_api_key,
        'needs_restart': needs_restart
    }


def stop_strategy(session: requests.Session, strategy_id: str) -> Tuple[bool, str]:
    """Stop a strategy."""
    try:
        resp = session.post(f"{BASE_URL}/python/stop/{strategy_id}")
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                # Wait for process to terminate
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
                time.sleep(1)  # Allow process to start
                return True, "Started"
            return False, data.get('message', 'Unknown error')
        return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)


def set_api_key(session: requests.Session, strategy_id: str, api_key: str) -> Tuple[bool, str]:
    """Set API key for a strategy (requires strategy to be stopped)."""
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


def restart_strategy(session: requests.Session, strategy_id: str) -> Tuple[bool, str]:
    """Restart a strategy."""
    # Stop first
    success, msg = stop_strategy(session, strategy_id)
    if not success:
        return False, f"Stop failed: {msg}"
    
    # Wait a bit
    time.sleep(2)
    
    # Start
    success, msg = start_strategy(session, strategy_id)
    if not success:
        return False, f"Start failed: {msg}"
    
    return True, "Restarted"


def main():
    """Main management function."""
    print("=" * 80)
    print("STRATEGY MANAGEMENT")
    print("=" * 80)
    
    # Login
    session = requests.Session()
    print("\n1. Logging in...")
    if not login_to_openalgo(session):
        print("❌ Login failed")
        return
    print("✅ Logged in")
    
    # Get strategies
    print("\n2. Loading strategies...")
    strategies = get_all_strategies(session)
    if not strategies:
        print("❌ No strategies found")
        return
    print(f"✅ Found {len(strategies)} strategies")
    
    # Load environment data
    env_data = {}
    if ENV_PATH.exists():
        env_data = json.loads(ENV_PATH.read_text())
    
    # Analyze strategies
    print("\n3. Analyzing strategies...")
    needs_api_key = []
    needs_restart = []
    
    for strategy_id, config in strategies.items():
        status = check_strategy_status(strategy_id, config, env_data)
        name = config.get('name', strategy_id)
        
        if not status['has_api_key']:
            needs_api_key.append((strategy_id, name))
        
        if status['needs_restart']:
            needs_restart.append((strategy_id, name))
    
    print(f"   Strategies needing API key: {len(needs_api_key)}")
    print(f"   Strategies needing restart: {len(needs_restart)}")
    
    # Set API keys
    if needs_api_key:
        print("\n4. Setting API keys...")
        for strategy_id, name in needs_api_key:
            print(f"   Processing: {name} ({strategy_id})")
            
            # Check if running
            config = strategies.get(strategy_id, {})
            was_running = config.get('is_running', False) and check_process_status(config.get('pid'))
            
            # Stop if running
            if was_running:
                success, msg = stop_strategy(session, strategy_id)
                if success:
                    print(f"     ✅ Stopped")
                else:
                    print(f"     ⚠️  Stop failed: {msg}")
                    continue
            
            # Set API key
            success, msg = set_api_key(session, strategy_id, API_KEY)
            if success:
                print(f"     ✅ API key set")
            else:
                print(f"     ⚠️  Failed: {msg}")
                continue
            
            # Restart if was running
            if was_running:
                time.sleep(1)
                success, msg = start_strategy(session, strategy_id)
                if success:
                    print(f"     ✅ Restarted")
                else:
                    print(f"     ⚠️  Restart failed: {msg}")
    
    # Restart strategies with bug fixes
    if needs_restart:
        print("\n5. Restarting strategies (bug fixes)...")
        for strategy_id, name in needs_restart:
            print(f"   Restarting: {name} ({strategy_id})")
            success, msg = restart_strategy(session, strategy_id)
            if success:
                print(f"     ✅ {msg}")
            else:
                print(f"     ⚠️  Failed: {msg}")
    
    print("\n" + "=" * 80)
    print("✅ Management complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
