import os
import json
import getpass
from pathlib import Path
from datetime import datetime

import requests


def _get_env_or_prompt(key, prompt, secret=False):
    value = os.environ.get(key, "").strip()
    if value:
        return value
    if secret:
        return getpass.getpass(prompt)
    return input(prompt).strip()


def _parse_strategy_inputs():
    # Default strategy set
    default_files = [
        "/Users/mac/dyad-apps/openalgo/strategies/scripts/ai_hybrid_reversion_breakout.py",
        "/Users/mac/dyad-apps/openalgo/strategies/scripts/advanced_ml_momentum_strategy.py",
        "/Users/mac/dyad-apps/openalgo/strategies/scripts/supertrend_vwap_strategy.py",
    ]
    default_names = ["AI Hybrid", "ML Momentum", "SuperTrend VWAP"]

    files_env = os.environ.get("STRATEGY_FILES", "").strip()
    names_env = os.environ.get("STRATEGY_NAMES", "").strip()

    if files_env:
        files = [f.strip() for f in files_env.split(",") if f.strip()]
    else:
        files = default_files

    if names_env:
        names = [n.strip() for n in names_env.split(",") if n.strip()]
        # Pad names if fewer than files
        while len(names) < len(files):
            names.append(Path(files[len(names)]).stem)
    else:
        names = default_names
        while len(names) < len(files):
            names.append(Path(files[len(names)]).stem)

    return list(zip(names, [Path(p) for p in files]))


def main():
    base_url = os.environ.get("OPENALGO_BASE_URL", "http://127.0.0.1:5001").rstrip("/")
    username = _get_env_or_prompt("OPENALGO_USERNAME", "OpenAlgo username: ")
    password = _get_env_or_prompt("OPENALGO_PASSWORD", "OpenAlgo password: ", secret=True)

    session = requests.Session()
    login_resp = session.post(f"{base_url}/auth/login", data={"username": username, "password": password})
    try:
        login_data = login_resp.json()
    except Exception:
        print(f"Login failed: non-JSON response (status {login_resp.status_code})")
        raise SystemExit(1)

    if login_data.get("status") != "success":
        print(f"Login failed: {login_data}")
        raise SystemExit(1)

    print("Login OK. Uploading strategies...")

    strategies = _parse_strategy_inputs()
    for name, path in strategies:
        if not path.exists():
            print(f"SKIP (missing): {path}")
            continue
        with path.open("rb") as f:
            files = {"strategy_file": (path.name, f, "text/x-python")}
            data = {"strategy_name": name}
            resp = session.post(f"{base_url}/python/new", data=data, files=files, allow_redirects=True)
            if resp.status_code not in (200, 302):
                print(f"Upload failed for {name}: {resp.status_code}")
            else:
                print(f"Uploaded: {name}")

    config_path = Path("/Users/mac/dyad-apps/openalgo/strategies/strategy_configs.json")
    if not config_path.exists():
        print("No strategy_configs.json found; cannot auto-start.")
        return

    configs = json.loads(config_path.read_text())
    file_to_id = {}
    for sid, cfg in configs.items():
        file_path = cfg.get("file_path", "")
        created_at = cfg.get("created_at", "")
        try:
            created_dt = datetime.fromisoformat(created_at) if created_at else datetime.min
        except Exception:
            created_dt = datetime.min
        file_to_id.setdefault(file_path, (datetime.min, None))
        if created_dt >= file_to_id[file_path][0]:
            file_to_id[file_path] = (created_dt, sid)

    print("Starting strategies...")
    for name, path in strategies:
        if not path.exists():
            continue
        match = file_to_id.get(str(path))
        if not match or not match[1]:
            print(f"No strategy ID found for {path}")
            continue
        sid = match[1]
        start_resp = session.post(f"{base_url}/python/start/{sid}")
        try:
            start_data = start_resp.json()
        except Exception:
            print(f"Start failed (non-JSON) for {name}: {start_resp.status_code}")
            continue
        print(f"Start {name}: {start_data}")

    print("Done.")


if __name__ == "__main__":
    main()
