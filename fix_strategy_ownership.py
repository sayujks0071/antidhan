#!/usr/bin/env python3
"""
Fix strategy ownership - update all strategies to belong to the current logged-in user
"""

import sys
import json

from pathlib import Path


def fix_strategy_ownership():
    """Update all strategies to belong to the correct user"""

    repo_root = Path(__file__).resolve().parent
    openalgo_dir = repo_root / "openalgo"
    sys.path.insert(0, str(openalgo_dir))

    # Load environment (DATABASE_URL, API_KEY_PEPPER, etc.)
    try:
        from dotenv import load_dotenv

        load_dotenv(openalgo_dir / ".env", override=False)
    except Exception:
        pass

    # Get the current user/session key from Auth DB
    from sqlalchemy import desc

    from database.auth_db import Auth, db_session

    auth_obj = Auth.query.filter_by(is_revoked=False).order_by(desc(Auth.id)).first()
    if not auth_obj:
        print("❌ No active Auth session found in database (auth table empty or revoked).")
        return

    user_session_key = auth_obj.name
    print(f"Found active auth user: {user_session_key} (broker={auth_obj.broker})")

    # Read strategy configs
    config_file = openalgo_dir / "strategies" / "strategy_configs.json"

    with open(config_file, "r", encoding="utf-8") as f:
        configs = json.load(f)

    print(f"Total strategies: {len(configs)}")

    # Update user_id for all strategies
    updated_count = 0
    for strategy_id, config in configs.items():
        old_user = config.get("user_id")
        if old_user != user_session_key:
            config["user_id"] = user_session_key
            updated_count += 1

    # Save updated configs
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(configs, f, indent=2, ensure_ascii=False)

    print(f"✅ Updated {updated_count} strategies to user: {user_session_key}")
    print("✅ Config file saved")

    db_session.remove()


if __name__ == "__main__":
    fix_strategy_ownership()
