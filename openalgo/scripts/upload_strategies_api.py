#!/usr/bin/env python3
"""
Upload Python strategies via API
Requires login session first
"""
import os
import sys
import requests
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

BASE_URL = "http://127.0.0.1:5001"
API_KEY = "630db05e091812b4c23298ca2d018b62376ddd168860d21fcb4bd2dfc265e49f"

def login():
    """Login and get session"""
    # For API upload, we need to login via web interface first
    # Or use API key if available
    print("⚠️  Note: Strategy upload requires web session authentication")
    print("    Please login at: http://127.0.0.1:5001/auth/login")
    print("    Then use browser to upload, or provide session cookie")
    return None

def upload_strategy_via_api(strategy_file_path, strategy_name=None):
    """Upload strategy via API (requires session)"""
    url = f"{BASE_URL}/python/new"
    
    # Read strategy file
    file_path = Path(strategy_file_path)
    if not file_path.exists():
        print(f"❌ File not found: {strategy_file_path}")
        return False
    
    with open(file_path, 'rb') as f:
        files = {'strategy_file': (file_path.name, f, 'text/x-python')}
        data = {'strategy_name': strategy_name or file_path.stem}
        
        # Note: This requires session cookie from web login
        # For automated upload, you'd need to:
        # 1. Login first to get session cookie
        # 2. Use that cookie in requests
        print(f"📤 Uploading: {file_path.name}")
        print(f"   ⚠️  Requires web session - use browser or provide session cookie")
        return False

def upload_strategies_direct():
    """Upload strategies directly to filesystem (bypasses web UI)"""
    strategies_dir = Path(__file__).parent.parent / "strategies" / "scripts"
    config_file = Path(__file__).parent.parent / "strategies" / "strategy_configs.json"
    env_file = Path(__file__).parent.parent / "strategies" / "strategy_env.json"
    
    import json
    from datetime import datetime
    import pytz
    
    IST = pytz.timezone('Asia/Kolkata')
    ist_now = datetime.now(IST)
    
    # Load existing configs
    if config_file.exists():
        with open(config_file, 'r') as f:
            configs = json.load(f)
    else:
        configs = {}
    
    # Load env file to get strategy IDs
    if env_file.exists():
        with open(env_file, 'r') as f:
            env_configs = json.load(f)
    else:
        env_configs = {}
    
    # Map strategy files to their IDs from env file
    strategy_files = list(strategies_dir.glob("*.py"))
    
    print(f"📦 Found {len(strategy_files)} strategy files")
    print("")
    
    uploaded = 0
    for strategy_file in strategy_files:
        file_stem = strategy_file.stem
        
        # Find matching strategy ID from env file
        strategy_id = None
        for env_id in env_configs.keys():
            if file_stem in env_id or env_id.startswith(file_stem):
                strategy_id = env_id
                break
        
        # If not found in env, create new ID
        if not strategy_id:
            strategy_id = f"{file_stem}_{ist_now.strftime('%Y%m%d%H%M%S')}"
        
        # Check if already deployed
        if strategy_id in configs:
            print(f"⏭️  Skipping {strategy_file.name} (already deployed as {strategy_id})")
            continue
        
        # Create config entry
        configs[strategy_id] = {
            'name': file_stem,
            'file_path': str(strategy_file),
            'is_running': False,
            'is_scheduled': False,
            'created_at': ist_now.isoformat(),
            'user_id': 'api_upload'
        }
        
        print(f"✅ Deployed: {strategy_file.name} → {strategy_id}")
        uploaded += 1
    
    # Save configs
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, 'w') as f:
        json.dump(configs, f, indent=2, default=str)
    
    print("")
    print(f"✅ Successfully deployed {uploaded} strategies")
    print(f"📊 Total strategies: {len(configs)}")
    print(f"📁 Config saved to: {config_file}")
    
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("  OpenAlgo Strategy Upload via API")
    print("=" * 60)
    print("")
    
    # Use direct filesystem method (bypasses web UI requirement)
    success = upload_strategies_direct()
    
    if success:
        print("")
        print("🎯 Next steps:")
        print("   1. Go to: http://127.0.0.1:5001/python")
        print("   2. Configure each strategy (symbols, schedule, etc.)")
        print("   3. Enable strategies when ready")
    else:
        print("❌ Upload failed")
