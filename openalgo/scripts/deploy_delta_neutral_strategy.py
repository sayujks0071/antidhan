#!/usr/bin/env python3
"""Deploy Delta Neutral Iron Condor Strategy"""
import os
import re
import time
import getpass
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


def main():
    base_url = os.environ.get("OPENALGO_BASE_URL", "http://127.0.0.1:5001").rstrip("/")
    username = _get_env_or_prompt("OPENALGO_USERNAME", "OpenAlgo username: ")
    password = _get_env_or_prompt("OPENALGO_PASSWORD", "OpenAlgo password: ", secret=True)
    api_key = _get_env_or_prompt("OPENALGO_APIKEY", "OpenAlgo API key: ", secret=True)
    
    session = requests.Session()
    
    # Login
    print("Logging in...")
    login_resp = session.post(f"{base_url}/auth/login", data={"username": username, "password": password})
    try:
        login_data = login_resp.json()
    except Exception:
        print(f"Login failed: non-JSON response (status {login_resp.status_code})")
        return
    
    if login_data.get("status") != "success":
        print(f"Login failed: {login_data}")
        return
    
    print("✅ Login successful")
    
    # Get CSRF token for upload
    print("Fetching CSRF token...")
    upload_csrf = _fetch_csrf(session, f"{base_url}/python/new")
    if not upload_csrf:
        print("⚠️  Could not fetch CSRF token, trying without it...")
    
    # Upload strategy
    strategy_file = Path("/Users/mac/dyad-apps/openalgo/strategies/scripts/delta_neutral_iron_condor_nifty.py")
    if not strategy_file.exists():
        print(f"❌ Strategy file not found: {strategy_file}")
        return
    
    print(f"Uploading strategy: {strategy_file.name}...")
    with strategy_file.open("rb") as f:
        files = {"strategy_file": (strategy_file.name, f, "text/x-python")}
        data = {"strategy_name": "Delta Neutral Iron Condor NIFTY"}
        if upload_csrf:
            data["csrf_token"] = upload_csrf
        resp = session.post(f"{base_url}/python/new", data=data, files=files, allow_redirects=False)
    
    if resp.status_code not in (200, 302):
        print(f"❌ Upload failed: HTTP {resp.status_code}")
        print(resp.text[:500])
        return
    
    print("✅ Strategy uploaded successfully")
    time.sleep(2)  # Allow server to process
    
    # Find strategy ID from configs
    import json
    config_path = Path("/Users/mac/dyad-apps/openalgo/strategies/strategy_configs.json")
    if config_path.exists():
        configs = json.loads(config_path.read_text())
        strategy_id = None
        for sid, cfg in configs.items():
            if "delta_neutral_iron_condor_nifty" in cfg.get("file_path", "").lower():
                strategy_id = sid
                break
        
        if strategy_id:
            print(f"Found strategy ID: {strategy_id}")
            
            # Set API key
            print("Setting API key...")
            env_csrf = _fetch_csrf(session, f"{base_url}/python/env/{strategy_id}")
            if env_csrf:
                env_resp = session.post(
                    f"{base_url}/python/env/{strategy_id}",
                    json={"OPENALGO_APIKEY": api_key},
                    headers={"X-CSRFToken": env_csrf, "Content-Type": "application/json"},
                    allow_redirects=False
                )
                if env_resp.status_code in (200, 302):
                    print("✅ API key set successfully")
                else:
                    print(f"⚠️  API key setting failed: HTTP {env_resp.status_code}")
            
            # Start strategy
            print("Starting strategy...")
            start_csrf = _fetch_csrf(session, f"{base_url}/python")
            if start_csrf:
                start_resp = session.post(
                    f"{base_url}/python/start/{strategy_id}",
                    headers={"X-CSRFToken": start_csrf, "Content-Type": "application/json"},
                    allow_redirects=False
                )
                if start_resp.status_code in (200, 302):
                    try:
                        start_data = start_resp.json()
                        if start_data.get("success"):
                            print("✅ Strategy started successfully")
                            print(f"   Message: {start_data.get('message', '')}")
                        else:
                            print(f"⚠️  Start response: {start_data}")
                    except:
                        print("✅ Strategy start request sent (check status)")
                else:
                    print(f"⚠️  Start failed: HTTP {start_resp.status_code}")
                    print(start_resp.text[:500])
        else:
            print("⚠️  Could not find strategy ID in configs")
            print("   Please start the strategy manually from the web UI")
    else:
        print("⚠️  Config file not found, cannot auto-start")
        print("   Please start the strategy manually from the web UI")
    
    print("\n" + "=" * 80)
    print("Deployment complete!")
    print("=" * 80)
    print(f"Strategy: Delta Neutral Iron Condor NIFTY")
    print(f"Access dashboard: {base_url}/python")
    print("=" * 80)


if __name__ == "__main__":
    main()
