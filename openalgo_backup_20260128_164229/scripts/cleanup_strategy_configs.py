#!/usr/bin/env python3
"""
Clean up strategy configs - remove utility scripts and duplicates
"""
import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent / "strategies" / "strategy_configs.json"

# Utility scripts that shouldn't be strategies
UTILITY_SCRIPTS = {
    'fix_rate_limit',
    'test_api_key', 
    'optimize_strategies',
    'run_mcx_backtest'
}

def cleanup_configs():
    """Remove utility scripts and duplicate entries"""
    if not CONFIG_FILE.exists():
        print(f"❌ Config file not found: {CONFIG_FILE}")
        return
    
    with open(CONFIG_FILE, 'r') as f:
        configs = json.load(f)
    
    original_count = len(configs)
    removed = []
    duplicates = {}
    
    # Track strategies by name to find duplicates
    name_to_ids = {}
    for sid, cfg in configs.items():
        name = cfg.get('name', '')
        file_path = cfg.get('file_path', '')
        
        # Check if utility script
        if name in UTILITY_SCRIPTS:
            removed.append((sid, name, 'utility_script'))
            continue
        
        # Check if file is a utility script
        if any(util in file_path for util in UTILITY_SCRIPTS):
            removed.append((sid, name, 'utility_script'))
            continue
        
        # Track by name for duplicate detection
        if name not in name_to_ids:
            name_to_ids[name] = []
        name_to_ids[name].append(sid)
    
    # Find duplicates (keep the first one, remove others)
    for name, ids in name_to_ids.items():
        if len(ids) > 1:
            # Keep the first one, mark others for removal
            for sid in ids[1:]:
                removed.append((sid, name, 'duplicate'))
                duplicates[name] = ids[0]  # Keep this one
    
    # Remove marked entries
    for sid, name, reason in removed:
        if sid in configs:
            del configs[sid]
            print(f"✅ Removed: {name} ({reason})")
    
    # Save cleaned configs
    with open(CONFIG_FILE, 'w') as f:
        json.dump(configs, f, indent=2, default=str)
    
    print(f"\n📊 Summary:")
    print(f"   Original: {original_count} strategies")
    print(f"   Removed: {len(removed)} entries")
    print(f"   Remaining: {len(configs)} strategies")
    
    if duplicates:
        print(f"\n✅ Kept (removed duplicates):")
        for name, kept_id in duplicates.items():
            print(f"   - {name}: {kept_id}")

if __name__ == "__main__":
    print("=" * 60)
    print("  Cleanup Strategy Configs")
    print("=" * 60)
    print()
    cleanup_configs()
