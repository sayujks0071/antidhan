#!/usr/bin/env python3
"""Fix missing OPENALGO_APIKEY for running strategies."""
import os
import json
import getpass
import re
import time
from pathlib import Path
import requests

def _get_env_or_prompt(key: str, prompt: str, secret: bool = False) -> str:
    value = os.environ.get(key, "").strip()
    if value:
        return value
    if secret:
        return getpass.getpass(prompt)
    return input(prompt).strip()

def _extract_csrf_token(html: str) -> str | None:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return match.group(1) if match else None

def _fetch_csrf(session: requests.Session, url: str) -> str | None:
    resp = session.get(url, allow_redirects=True)
    if not resp.ok:
        return None
    return _extract_csrf_token(resp.text)

base_url = os.environ.get("OPENALGO_BASE_URL", "http://127.0.0.1:5001").rstrip("/")
api_key = _get_env_or_prompt("OPENALGO_APIKEY", "OpenAlgo API key: ", secret=True)
username = _get_env_or_prompt("OPENALGO_USERNAME", "OpenAlgo username: ")
password = _get_env_or_prompt("OPENALGO_PASSWORD", "OpenAlgo password: ", secret=True)

config_path = Path("/Users/mac/dyad-apps/openalgo/strategies/strategy_configs.json")

session = requests.Session()

# Login
for attempt in range(3):
    login_csrf = _fetch_csrf(session, f"{base_url}/auth/login")
    login_payload = {"username": username, "password": password}
    if login_csrf:
        login_payload["csrf_token"] = login_csrf
    login_resp = session.post(f"{base_url}/auth/login", data=login_payload)
    try:
        login_data = login_resp.json()
    except Exception:
        login_data = {}
    if login_data.get("error") == "Rate limit exceeded":
        wait_s = 65
        print(f"Login rate limited. Waiting {wait_s}s before retry...")
        time.sleep(wait_s)
        continue
    break

if login_resp.status_code != 200 or login_data.get("status") != "success":
    print(f"Login failed: {login_data}")
    raise SystemExit(1)

print("✅ Logged in successfully")

# Load strategy configs
if not config_path.exists():
    print("No strategy configs found")
    raise SystemExit(1)

configs = json.loads(config_path.read_text())
running_strategies = [(sid, cfg) for sid, cfg in configs.items() if cfg.get('is_running')]

if not running_strategies:
    print("No running strategies found")
    raise SystemExit(0)

print(f"\nFound {len(running_strategies)} running strategies")
print("Setting OPENALGO_APIKEY and restarting...\n")

for strategy_id, config in running_strategies:
    strategy_name = config.get('name', strategy_id)
    print(f"Processing: {strategy_name} (ID: {strategy_id})")
    
    # Stop the strategy first
    stop_resp = session.post(f"{base_url}/python/stop/{strategy_id}")
    try:
        stop_data = stop_resp.json()
        if stop_data.get('success'):
            print(f"  ✅ Stopped")
            time.sleep(2)
        else:
            print(f"  ⚠️  Stop response: {stop_data}")
    except Exception:
        print(f"  ⚠️  Stop failed: {stop_resp.status_code}")
    
    # Set environment variable
    env_csrf = _fetch_csrf(session, f"{base_url}/python/env/{strategy_id}")
    env_payload = {
        "regular_vars": {
            "OPENALGO_APIKEY": api_key
        },
        "secure_vars": {}
    }
    if env_csrf:
        # CSRF might not be needed for JSON POST, but include if form-based
        pass
    
    env_resp = session.post(
        f"{base_url}/python/env/{strategy_id}",
        json=env_payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        env_data = env_resp.json()
        if env_data.get('success'):
            print(f"  ✅ API key set")
        else:
            print(f"  ⚠️  Env update: {env_data}")
    except Exception:
        print(f"  ⚠️  Env update failed: {env_resp.status_code}")
    
    # Restart the strategy
    time.sleep(1)
    start_resp = session.post(f"{base_url}/python/start/{strategy_id}")
    try:
        start_data = start_resp.json()
        if start_data.get('success'):
            print(f"  ✅ Restarted")
        else:
            print(f"  ⚠️  Start: {start_data}")
    except Exception:
        print(f"  ⚠️  Start failed: {start_resp.status_code}")
    
    print()

print("✅ Done! Strategies should now have OPENALGO_APIKEY set.")
