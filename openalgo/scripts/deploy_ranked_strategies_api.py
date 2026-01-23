#!/usr/bin/env python3
"""Deploy top-ranked strategies using OpenAlgo API."""
import os
import csv
import json
import getpass
import re
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

import requests


STRATEGY_FILE_MAP = {
    "NIFTY Greeks Enhanced": "nifty_greeks_enhanced_20260122.py",
    "NIFTY Multi-Strike Momentum": "nifty_multistrike_momentum_20260122.py",
    "NIFTY AITRAPP Options Ranker": "nifty_aitrapp_options_ranker_20260122.py",
    "NIFTY Spread Strategy": "nifty_spread_strategy_20260122.py",
    "NIFTY Iron Condor": "nifty_iron_condor_20260122.py",
    "NIFTY Gamma Scalping": "nifty_gamma_scalping_20260122.py",
    "SENSEX Greeks Enhanced": "sensex_greeks_enhanced_20260122.py",
    "SENSEX Multi-Strike Momentum": "sensex_multistrike_momentum_20260122.py",
}


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


def read_rankings(csv_path: Path) -> List[Dict]:
    rankings = []
    if not csv_path.exists():
        print(f"Rankings file not found: {csv_path}")
        return rankings

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rankings.append({
                "rank": int(row.get("rank", 0)),
                "strategy": row.get("strategy", ""),
                "score": float(row.get("score", 0)),
                "total_trades": int(row.get("total_trades", 0)),
            })

    return sorted(rankings, key=lambda x: x["rank"])


def get_strategy_file(strategy_name: str, scripts_dir: Path) -> Path | None:
    filename = STRATEGY_FILE_MAP.get(strategy_name)
    if not filename:
        for key, value in STRATEGY_FILE_MAP.items():
            if strategy_name.lower() in key.lower() or key.lower() in strategy_name.lower():
                filename = value
                break
    if not filename:
        return None
    
    # Try openalgo scripts directory first
    file_path = scripts_dir / filename
    if file_path.exists():
        return file_path
    
    # Try AITRAPP folder as fallback
    aitrapp_scripts = Path("/Users/mac/dyad-apps/AITRAPP/AITRAPP/packages/core/strategies")
    aitrapp_file = aitrapp_scripts / filename
    if aitrapp_file.exists():
        return aitrapp_file
    
    # Return the openalgo path even if it doesn't exist (will fail with clear error)
    return file_path


def _created_at_ts(created_at: str) -> float:
    if not created_at:
        return 0.0
    try:
        dt = datetime.fromisoformat(created_at)
    except Exception:
        return 0.0
    try:
        return dt.timestamp()
    except Exception:
        return 0.0


def latest_ids_by_file(config_path: Path, base_dir: Path) -> Dict[str, str]:
    if not config_path.exists():
        return {}
    configs = json.loads(config_path.read_text())
    file_to_id: Dict[str, Tuple[float, str | None]] = {}
    for sid, cfg in configs.items():
        file_path = cfg.get("file_path", "")
        if file_path:
            file_path_obj = Path(file_path)
            if not file_path_obj.is_absolute():
                file_path_obj = (base_dir / file_path_obj).resolve()
            file_path = file_path_obj.as_posix()
        created_at = cfg.get("created_at", "")
        created_ts = _created_at_ts(created_at)
        current = file_to_id.get(file_path, (0.0, None))
        if created_ts >= current[0]:
            file_to_id[file_path] = (created_ts, sid)
    return {k: v for k, (_, v) in file_to_id.items() if v}


def latest_ids_by_stem(config_path: Path, base_dir: Path) -> Dict[str, str]:
    if not config_path.exists():
        return {}
    configs = json.loads(config_path.read_text())
    stem_to_id: Dict[str, Tuple[float, str | None]] = {}
    for sid, cfg in configs.items():
        file_path = cfg.get("file_path", "")
        if file_path:
            file_path_obj = Path(file_path)
            if not file_path_obj.is_absolute():
                file_path_obj = (base_dir / file_path_obj).resolve()
            stem = file_path_obj.stem
        else:
            continue
        created_ts = _created_at_ts(cfg.get("created_at", ""))
        current = stem_to_id.get(stem, (0.0, None))
        if created_ts >= current[0]:
            stem_to_id[stem] = (created_ts, sid)
    return {k: v for k, (_, v) in stem_to_id.items() if v}


def main() -> None:
    base_url = os.environ.get("OPENALGO_BASE_URL", "http://127.0.0.1:5001").rstrip("/")
    rankings_csv = Path(os.environ.get(
        "RANKINGS_CSV",
        "/Users/mac/dyad-apps/openalgo/strategies/openalgo/strategies/backtest_results/strategy_rankings.csv"
    ))
    top_n = int(os.environ.get("TOP_N", "3"))
    min_score = float(os.environ.get("MIN_SCORE", "0"))
    min_trades = int(os.environ.get("MIN_TRADES", "0"))
    dry_run = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")

    # Check if strategies are in AITRAPP folder first, then fallback to openalgo
    aitrapp_scripts = Path("/Users/mac/dyad-apps/AITRAPP/AITRAPP/packages/core/strategies")
    base_dir = Path("/Users/mac/dyad-apps/openalgo")
    scripts_dir = base_dir / "strategies" / "scripts"
    config_path = base_dir / "strategies" / "strategy_configs.json"

    username = _get_env_or_prompt("OPENALGO_USERNAME", "OpenAlgo username: ")
    password = _get_env_or_prompt("OPENALGO_PASSWORD", "OpenAlgo password: ", secret=True)

    session = requests.Session()
    # Login with retry on rate limit
    login_resp = None
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
    if login_resp is None:
        print("Login failed: no response")
        raise SystemExit(1)
    try:
        login_data = login_resp.json()
    except Exception:
        print(f"Login failed: non-JSON response (status {login_resp.status_code})")
        raise SystemExit(1)

    if login_data.get("status") != "success":
        if login_data.get("error") == "Rate limit exceeded":
            print("Login rate limit exceeded. Wait 60s and retry.")
        else:
            print(f"Login failed: {login_data}")
        raise SystemExit(1)

    rankings = read_rankings(rankings_csv)
    if not rankings:
        print("No rankings found. Aborting.")
        return

    print(f"Found {len(rankings)} ranked strategies. Deploying top {top_n}...")

    selected = []
    for entry in rankings[:top_n]:
        if entry["score"] < min_score:
            continue
        if entry["total_trades"] < min_trades:
            continue
        selected.append(entry)

    if not selected:
        print("No strategies passed filters.")
        return

    if dry_run:
        print("DRY_RUN enabled. Selected strategies:")
        for entry in selected:
            print(f"- {entry['strategy']} (score={entry['score']}, trades={entry['total_trades']})")
        return

    upload_csrf = _fetch_csrf(session, f"{base_url}/python/new")

    # Get existing strategies before upload
    stem_to_id_before = latest_ids_by_stem(config_path, base_dir)

    for entry in selected:
        strategy_name = entry["strategy"]
        strategy_file = get_strategy_file(strategy_name, scripts_dir)
        if not strategy_file or not strategy_file.exists():
            print(f"SKIP (missing file): {strategy_name} at {strategy_file}")
            continue
        
        # Check if already uploaded by filename stem
        base_stem = strategy_file.stem
        already_uploaded = any(stem.startswith(base_stem) for stem in stem_to_id_before.keys())
        if already_uploaded:
            print(f"SKIP (already uploaded): {strategy_name}")
            continue
        
        attempt = 0
        while attempt < 3:
            attempt += 1
            with strategy_file.open("rb") as f:
                files = {"strategy_file": (strategy_file.name, f, "text/x-python")}
                data = {"strategy_name": strategy_name}
                if upload_csrf:
                    data["csrf_token"] = upload_csrf
                resp = session.post(f"{base_url}/python/new", data=data, files=files, allow_redirects=False)
            if resp.status_code in (200, 302):
                redirect_url = resp.headers.get('Location', '') if resp.status_code == 302 else ''
                # Check if redirect is to login (session expired)
                if '/auth/login' in redirect_url or '/login' in redirect_url:
                    print(f"Session expired during upload for {strategy_name}, re-logging in...")
                    # Re-login
                    login_csrf = _fetch_csrf(session, f"{base_url}/auth/login")
                    login_payload = {"username": username, "password": password}
                    if login_csrf:
                        login_payload["csrf_token"] = login_csrf
                    login_resp = session.post(f"{base_url}/auth/login", data=login_payload)
                    # Refresh CSRF token
                    upload_csrf = _fetch_csrf(session, f"{base_url}/python/new")
                    if attempt < 3:
                        time.sleep(2)
                        continue
                    else:
                        print(f"Failed to maintain session for {strategy_name}")
                        break
                # Check if response contains success message or redirects to /python/
                resp_text = resp.text[:500] if resp.text else ""
                if ("uploaded successfully" in resp_text.lower() or 
                    "success" in resp_text.lower() or 
                    resp.status_code == 302 and '/python' in redirect_url):
                    print(f"Uploaded: {strategy_name} (status: {resp.status_code})")
                    # If redirected, follow to ensure upload completed and session persists
                    if resp.status_code == 302 and redirect_url:
                        if not redirect_url.startswith('http'):
                            redirect_url = f"{base_url}{redirect_url}"
                        session.get(redirect_url)
                    # Small delay to ensure file write completes
                    time.sleep(1)
                    uploaded_count += 1
                    break
                else:
                    print(f"Upload may have failed for {strategy_name}: unexpected response")
                    if attempt < 3:
                        time.sleep(2)
                        continue
            if resp.status_code == 429 and attempt < 3:
                print(f"Rate limited on upload for {strategy_name}, retrying in 10s...")
                time.sleep(10)
                continue
            print(f"Upload failed for {strategy_name}: {resp.status_code}")
            if resp.text:
                print(f"  Response: {resp.text[:200]}")
            break

    # Wait a moment for config file to be written
    time.sleep(3)
    # Reload config file after uploads - check multiple times for file write
    for retry in range(3):
        if config_path.exists():
            try:
                file_to_id = latest_ids_by_file(config_path, base_dir)
                stem_to_id = latest_ids_by_stem(config_path, base_dir)
                break
            except Exception:
                if retry < 2:
                    time.sleep(1)
                    continue
        else:
            if retry < 2:
                time.sleep(1)
                continue
    else:
        file_to_id = {}
        stem_to_id = {}

    # Try to get strategy list from status endpoint
    status_resp = session.get(f"{base_url}/python/status")
    status_ids = {}
    try:
        status_data = status_resp.json()
        for item in status_data.get("strategies", []):
            if item.get("name") and item.get("id"):
                status_ids[item["name"]] = item["id"]
    except Exception:
        # If status endpoint fails, reload config and match by name
        if config_path.exists():
            try:
                configs = json.loads(config_path.read_text())
                for sid, cfg in configs.items():
                    cfg_name = cfg.get("name", "")
                    if cfg_name:
                        status_ids[cfg_name] = sid
            except Exception:
                pass
    
    print("Starting strategies...")
    for entry in selected:
        strategy_name = entry["strategy"]
        strategy_file = get_strategy_file(strategy_name, scripts_dir)
        if not strategy_file:
            continue
        
        # Try multiple matching strategies
        sid = status_ids.get(strategy_name)
        if not sid:
            # Try partial name match
            for name, strategy_id in status_ids.items():
                if strategy_name.lower() in name.lower() or name.lower() in strategy_name.lower():
                    sid = strategy_id
                    print(f"Matched '{strategy_name}' to '{name}' (ID: {sid})")
                    break
        
        if not sid:
            sid = file_to_id.get(strategy_file.resolve().as_posix())
        if not sid:
            base_stem = strategy_file.stem
            # match any stem that starts with base stem
            candidates = {stem: sid for stem, sid in stem_to_id.items() if stem.startswith(base_stem)}
            if candidates:
                # pick the lexicographically latest stem as a proxy for latest upload
                sid = candidates[sorted(candidates.keys())[-1]]
        
        # Last resort: find strategies created in last 5 minutes with matching file
        if not sid and config_path.exists():
            try:
                configs = json.loads(config_path.read_text())
                now_ts = datetime.now().timestamp()
                for cfg_id, cfg in configs.items():
                    cfg_file = cfg.get("file_path", "")
                    cfg_created = _created_at_ts(cfg.get("created_at", ""))
                    # Check if created in last 5 minutes and file matches
                    if (now_ts - cfg_created < 300 and 
                        strategy_file.name in cfg_file):
                        sid = cfg_id
                        print(f"Found recently uploaded strategy: {cfg_id} for {strategy_name}")
                        break
            except Exception:
                pass
        
        if not sid:
            print(f"No strategy ID found for {strategy_name} (tried: name match, file path, stem match, recent upload)")
            if status_ids:
                print(f"  Available strategies: {list(status_ids.keys())[:5]}...")
            continue
        start_resp = session.post(f"{base_url}/python/start/{sid}")
        try:
            start_data = start_resp.json()
        except Exception:
            print(f"Start failed (non-JSON) for {strategy_name}: {start_resp.status_code}")
            continue
        print(f"Start {strategy_name}: {start_data}")

    print("Done.")


if __name__ == "__main__":
    main()
