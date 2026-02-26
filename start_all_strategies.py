#!/usr/bin/env python3
"""
Start all scheduled trading strategies in OpenAlgo
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
OPENALGO_DIR = REPO_ROOT / "openalgo"


def load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(OPENALGO_DIR / ".env", override=False)
    except Exception:
        pass


def get_active_auth_user() -> str | None:
    try:
        from sqlalchemy import desc

        from database.auth_db import Auth

        auth_obj = Auth.query.filter_by(is_revoked=False).order_by(desc(Auth.id)).first()
        return auth_obj.name if auth_obj else None
    except Exception:
        return None


def repair_strategy_ownership(config_path: Path, desired_user_id: str) -> int:
    with open(config_path, "r", encoding="utf-8") as f:
        configs = json.load(f)

    updated = 0
    for _, cfg in configs.items():
        if isinstance(cfg, dict) and cfg.get("user_id") != desired_user_id:
            cfg["user_id"] = desired_user_id
            updated += 1

    if updated:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(configs, f, indent=2, ensure_ascii=False)
    return updated


def start_all_strategies(within_window_only: bool, repair: bool) -> int:
    """Start scheduled strategies using the local Python Strategy manager (no HTTP/session needed)."""
    sys.path.insert(0, str(OPENALGO_DIR))
    load_env()
    os.chdir(OPENALGO_DIR)

    config_path = OPENALGO_DIR / "strategies" / "strategy_configs.json"
    if repair:
        active_user = get_active_auth_user()
        if active_user:
            updated = repair_strategy_ownership(config_path, active_user)
            if updated:
                print(f"🔧 Repaired ownership: updated {updated} strategies to user_id={active_user}")

    # Import after env + path are set
    from blueprints.python_strategy import (
        STRATEGY_CONFIGS,
        cleanup_dead_processes,
        is_within_schedule_time,
        load_configs,
        start_strategy_process,
    )

    load_configs()
    cleanup_dead_processes()

    candidates: list[str] = []
    eligible_total = 0
    for strategy_id, cfg in STRATEGY_CONFIGS.items():
        if not isinstance(cfg, dict):
            continue
        if not cfg.get("is_scheduled"):
            continue
        if cfg.get("manually_stopped"):
            continue
        eligible_total += 1
        if within_window_only and not is_within_schedule_time(strategy_id):
            continue
        if cfg.get("is_running"):
            continue
        candidates.append(strategy_id)

    if not candidates:
        if within_window_only and eligible_total:
            print("ℹ️  No scheduled strategies eligible to start right now (outside schedule window).")
            print("    Use `--all` to start anyway (not recommended for live trading).")
        else:
            print("✅ No scheduled strategies to start.")
        return 0

    print(f"Found {len(candidates)} scheduled strategies to start:")
    print(f"{'=' * 70}")

    started = []
    failed = []

    for strategy_id in candidates:
        cfg = STRATEGY_CONFIGS.get(strategy_id, {}) if isinstance(STRATEGY_CONFIGS, dict) else {}
        strategy_name = cfg.get("name", strategy_id) if isinstance(cfg, dict) else strategy_id
        print(f"\n▶️  Starting: {strategy_name}...")

        try:
            success, message = start_strategy_process(strategy_id)
            if success:
                print("   ✅ Started successfully")
                started.append(strategy_name)
            else:
                print(f"   ❌ Failed: {message}")
                failed.append((strategy_name, message))

            # Small delay to avoid overwhelming the system
            time.sleep(0.5)

        except Exception as e:
            print(f"   ❌ Error: {e}")
            failed.append((strategy_name, str(e)))

    # Summary
    print(f"\n{'=' * 70}")
    print("📊 Summary:")
    print(f"   ✅ Started: {len(started)}")
    print(f"   ❌ Failed:  {len(failed)}")

    if started:
        print("\n   Started strategies:")
        for name in started:
            print(f"     • {name}")

    if failed:
        print("\n   Failed strategies:")
        for name, reason in failed:
            print(f"     • {name}: {reason}")

    print(f"\n{'=' * 70}")
    print("✅ Done!")
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="Start scheduled OpenAlgo strategies locally")
        parser.add_argument(
            "--all",
            action="store_true",
            help="Start scheduled strategies even outside the time window",
        )
        parser.add_argument(
            "--no-repair",
            action="store_true",
            help="Skip ownership repair (user_id) before starting",
        )
        args = parser.parse_args()
        raise SystemExit(start_all_strategies(within_window_only=not args.all, repair=not args.no_repair))
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
