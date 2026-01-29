#!/usr/bin/env python3
"""
Save Current Settings for Future Trading Days

Backs up strategy configurations, environment variables, and optionally server settings.
Creates timestamped backups in openalgo/backups/ directory.
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Paths
SCRIPT_DIR = Path(__file__).parent
OPENALGO_DIR = SCRIPT_DIR.parent
BACKUPS_DIR = OPENALGO_DIR / "backups"
STRATEGIES_DIR = OPENALGO_DIR / "strategies"

# Files to backup
STRATEGY_CONFIGS_FILE = STRATEGIES_DIR / "strategy_configs.json"
STRATEGY_ENV_FILE = STRATEGIES_DIR / "strategy_env.json"
ENV_FILE = OPENALGO_DIR / ".env"

def get_openalgo_version() -> str:
    """Try to get OpenAlgo version from app.py or return unknown"""
    try:
        app_file = OPENALGO_DIR / "app.py"
        if app_file.exists():
            content = app_file.read_text()
            # Look for version string
            for line in content.split('\n'):
                if 'version' in line.lower() or '__version__' in line:
                    # Try to extract version
                    import re
                    match = re.search(r'["\'](\d+\.\d+\.\d+[^"\']*)["\']', line)
                    if match:
                        return match.group(1)
    except Exception:
        pass
    return "unknown"

def count_running_strategies(configs: Dict) -> int:
    """Count strategies marked as running"""
    return sum(1 for cfg in configs.values() if cfg.get('is_running', False))

def create_backup(include_env: bool = False) -> Optional[Path]:
    """
    Create a backup of current settings.
    
    Args:
        include_env: Whether to include .env file (contains sensitive data)
    
    Returns:
        Path to backup directory if successful, None otherwise
    """
    # Create backups directory if it doesn't exist
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create timestamped backup directory
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_dir = BACKUPS_DIR / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*60}")
    print(f"Creating backup: {timestamp}")
    print(f"{'='*60}\n")
    
    backed_up_files = []
    errors = []
    
    # Backup strategy_configs.json
    if STRATEGY_CONFIGS_FILE.exists():
        try:
            dest = backup_dir / "strategy_configs.json"
            shutil.copy2(STRATEGY_CONFIGS_FILE, dest)
            backed_up_files.append("strategy_configs.json")
            
            # Count running strategies
            with open(STRATEGY_CONFIGS_FILE, 'r') as f:
                configs = json.load(f)
            running_count = count_running_strategies(configs)
            total_count = len(configs)
            print(f"✅ Backed up strategy_configs.json ({total_count} strategies, {running_count} running)")
        except Exception as e:
            errors.append(f"Failed to backup strategy_configs.json: {e}")
            print(f"❌ Error backing up strategy_configs.json: {e}")
    else:
        print(f"⚠️  strategy_configs.json not found (skipping)")
    
    # Backup strategy_env.json
    if STRATEGY_ENV_FILE.exists():
        try:
            dest = backup_dir / "strategy_env.json"
            shutil.copy2(STRATEGY_ENV_FILE, dest)
            backed_up_files.append("strategy_env.json")
            
            # Count strategies with env vars
            with open(STRATEGY_ENV_FILE, 'r') as f:
                env_data = json.load(f)
            print(f"✅ Backed up strategy_env.json ({len(env_data)} strategies configured)")
        except Exception as e:
            errors.append(f"Failed to backup strategy_env.json: {e}")
            print(f"❌ Error backing up strategy_env.json: {e}")
    else:
        print(f"⚠️  strategy_env.json not found (skipping)")
    
    # Backup .env (optional, with warning)
    if include_env:
        if ENV_FILE.exists():
            try:
                dest = backup_dir / ".env"
                shutil.copy2(ENV_FILE, dest)
                backed_up_files.append(".env")
                print(f"✅ Backed up .env (contains sensitive credentials)")
            except Exception as e:
                errors.append(f"Failed to backup .env: {e}")
                print(f"❌ Error backing up .env: {e}")
        else:
            print(f"⚠️  .env not found (skipping)")
    else:
        print(f"ℹ️  Skipping .env backup (use --include-env to backup)")
    
    # Create manifest file
    manifest = {
        "backup_timestamp": timestamp,
        "backup_date": datetime.now().isoformat(),
        "files_backed_up": backed_up_files,
        "openalgo_version": get_openalgo_version(),
        "backup_location": str(backup_dir),
        "errors": errors if errors else None
    }
    
    # Add strategy counts if configs were backed up
    if STRATEGY_CONFIGS_FILE.exists():
        try:
            with open(STRATEGY_CONFIGS_FILE, 'r') as f:
                configs = json.load(f)
            manifest["strategy_count"] = len(configs)
            manifest["running_strategies_count"] = count_running_strategies(configs)
        except Exception:
            pass
    
    manifest_file = backup_dir / "backup_manifest.json"
    try:
        with open(manifest_file, 'w') as f:
            json.dump(manifest, f, indent=2)
        backed_up_files.append("backup_manifest.json")
        print(f"✅ Created backup_manifest.json")
    except Exception as e:
        errors.append(f"Failed to create manifest: {e}")
        print(f"❌ Error creating manifest: {e}")
    
    # Update 'latest' symlink
    latest_link = BACKUPS_DIR / "latest"
    try:
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        latest_link.symlink_to(backup_dir.name)
        print(f"✅ Updated 'latest' symlink")
    except Exception as e:
        print(f"⚠️  Could not create 'latest' symlink: {e}")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"Backup Summary")
    print(f"{'='*60}")
    print(f"Backup location: {backup_dir}")
    print(f"Files backed up: {len(backed_up_files)}")
    if errors:
        print(f"Errors: {len(errors)}")
        for error in errors:
            print(f"  - {error}")
    print(f"{'='*60}\n")
    
    if errors and len(backed_up_files) == 0:
        # If all backups failed, remove the empty directory
        try:
            backup_dir.rmdir()
            return None
        except Exception:
            pass
    
    return backup_dir

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Backup current OpenAlgo settings for future trading days"
    )
    parser.add_argument(
        "--include-env",
        action="store_true",
        help="Include .env file in backup (contains sensitive credentials)"
    )
    
    args = parser.parse_args()
    
    # Warn about .env backup
    if args.include_env:
        print("\n⚠️  WARNING: .env file contains sensitive credentials (API keys, secrets)")
        print("   This backup will include your broker credentials and security keys.")
        print("   Ensure backups are stored securely.\n")
        response = input("Continue with .env backup? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            print("Skipping .env backup.")
            args.include_env = False
    
    backup_dir = create_backup(include_env=args.include_env)
    
    if backup_dir:
        print(f"✅ Backup completed successfully!")
        print(f"\nTo restore this backup, run:")
        print(f"  python3 scripts/restore_settings.py")
        print(f"\nTo list all backups, run:")
        print(f"  python3 scripts/list_backups.py")
        return 0
    else:
        print(f"❌ Backup failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
