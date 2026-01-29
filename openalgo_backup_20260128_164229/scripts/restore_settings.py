#!/usr/bin/env python3
"""
Restore Settings from Backup

Restores strategy configurations and environment variables from a previous backup.
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

# Files to restore
STRATEGY_CONFIGS_FILE = STRATEGIES_DIR / "strategy_configs.json"
STRATEGY_ENV_FILE = STRATEGIES_DIR / "strategy_env.json"
ENV_FILE = OPENALGO_DIR / ".env"

def list_backups() -> List[Path]:
    """List all available backups, sorted by timestamp (newest first)"""
    if not BACKUPS_DIR.exists():
        return []
    
    backups = []
    for item in BACKUPS_DIR.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            manifest = item / "backup_manifest.json"
            if manifest.exists():
                backups.append(item)
    
    # Sort by directory name (timestamp) descending
    backups.sort(key=lambda x: x.name, reverse=True)
    return backups

def load_manifest(backup_dir: Path) -> Optional[Dict]:
    """Load backup manifest"""
    manifest_file = backup_dir / "backup_manifest.json"
    if not manifest_file.exists():
        return None
    
    try:
        with open(manifest_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading manifest: {e}")
        return None

def validate_json_file(file_path: Path) -> bool:
    """Validate that a file is valid JSON"""
    if not file_path.exists():
        return False
    
    try:
        with open(file_path, 'r') as f:
            json.load(f)
        return True
    except json.JSONDecodeError:
        return False

def restore_file(source: Path, dest: Path, description: str, create_backup: bool = True) -> bool:
    """
    Restore a file from backup.
    
    Args:
        source: Source file in backup directory
        dest: Destination file path
        description: Description of file being restored
        create_backup: Whether to backup current file before overwriting
    
    Returns:
        True if successful, False otherwise
    """
    if not source.exists():
        print(f"⚠️  {description} not found in backup (skipping)")
        return False
    
    # Validate JSON before restoring
    if source.suffix == '.json':
        if not validate_json_file(source):
            print(f"❌ {description} is invalid JSON (skipping)")
            return False
    
    # Backup current file if it exists
    if create_backup and dest.exists():
        backup_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dest = dest.parent / f"{dest.name}.backup_{backup_timestamp}"
        try:
            shutil.copy2(dest, backup_dest)
            print(f"✅ Backed up current {description} to {backup_dest.name}")
        except Exception as e:
            print(f"⚠️  Could not backup current {description}: {e}")
    
    # Restore file
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        print(f"✅ Restored {description}")
        return True
    except Exception as e:
        print(f"❌ Error restoring {description}: {e}")
        return False

def reset_process_state(configs: Dict) -> Dict:
    """Reset is_running and pid fields to prevent stale process references"""
    reset_count = 0
    for strategy_id, config in configs.items():
        if config.get('is_running', False) or config.get('pid'):
            config['is_running'] = False
            config['pid'] = None
            reset_count += 1
    
    if reset_count > 0:
        print(f"ℹ️  Reset process state for {reset_count} strategies (is_running=False, pid=None)")
    
    return configs

def restore_backup(backup_dir: Path, reset_processes: bool = True, include_env: bool = False) -> bool:
    """
    Restore settings from a backup directory.
    
    Args:
        backup_dir: Path to backup directory
        reset_processes: Whether to reset is_running and pid fields
        include_env: Whether to restore .env file
    
    Returns:
        True if successful, False otherwise
    """
    manifest = load_manifest(backup_dir)
    if manifest:
        print(f"\n{'='*60}")
        print(f"Restoring backup: {manifest.get('backup_timestamp', backup_dir.name)}")
        print(f"Backup date: {manifest.get('backup_date', 'unknown')}")
        if 'strategy_count' in manifest:
            print(f"Strategies: {manifest['strategy_count']} total, {manifest.get('running_strategies_count', 0)} running")
        print(f"{'='*60}\n")
    else:
        print(f"\n{'='*60}")
        print(f"Restoring backup: {backup_dir.name}")
        print(f"{'='*60}\n")
    
    success_count = 0
    
    # Restore strategy_configs.json
    source_configs = backup_dir / "strategy_configs.json"
    if source_configs.exists():
        # Load and optionally reset process state
        if reset_processes:
            try:
                with open(source_configs, 'r') as f:
                    configs = json.load(f)
                configs = reset_process_state(configs)
                
                # Write modified configs to temp file, then copy
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
                    json.dump(configs, tmp, indent=2, default=str, ensure_ascii=False)
                    tmp_path = Path(tmp.name)
                
                if restore_file(tmp_path, STRATEGY_CONFIGS_FILE, "strategy_configs.json"):
                    tmp_path.unlink()  # Clean up temp file
                    success_count += 1
            except Exception as e:
                print(f"❌ Error processing strategy_configs.json: {e}")
                # Fallback to direct restore
                if restore_file(source_configs, STRATEGY_CONFIGS_FILE, "strategy_configs.json"):
                    success_count += 1
        else:
            if restore_file(source_configs, STRATEGY_CONFIGS_FILE, "strategy_configs.json"):
                success_count += 1
    
    # Restore strategy_env.json
    source_env = backup_dir / "strategy_env.json"
    if restore_file(source_env, STRATEGY_ENV_FILE, "strategy_env.json"):
        success_count += 1
    
    # Restore .env (optional)
    if include_env:
        source_env_file = backup_dir / ".env"
        if restore_file(source_env_file, ENV_FILE, ".env (server configuration)", create_backup=True):
            success_count += 1
            print(f"\n⚠️  IMPORTANT: Server configuration (.env) has been restored.")
            print(f"   You may need to restart the server for changes to take effect.")
    else:
        print(f"ℹ️  Skipping .env restore (use --include-env to restore)")
    
    print(f"\n{'='*60}")
    print(f"Restore Summary")
    print(f"{'='*60}")
    print(f"Files restored: {success_count}")
    print(f"{'='*60}\n")
    
    return success_count > 0

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Restore OpenAlgo settings from a backup"
    )
    parser.add_argument(
        "--backup",
        type=str,
        help="Backup directory name or path (e.g., '2026-01-27_115500' or 'latest')"
    )
    parser.add_argument(
        "--include-env",
        action="store_true",
        help="Restore .env file (contains sensitive credentials)"
    )
    parser.add_argument(
        "--no-reset-processes",
        action="store_true",
        help="Don't reset is_running and pid fields (may cause stale process references)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be restored without making changes"
    )
    
    args = parser.parse_args()
    
    # List available backups
    backups = list_backups()
    
    if not backups:
        print("❌ No backups found!")
        print(f"   Create a backup first with: python3 scripts/save_settings.py")
        return 1
    
    # Select backup
    backup_dir = None
    
    if args.backup:
        # Find backup by name or path
        if args.backup == "latest":
            # Use latest symlink
            latest_link = BACKUPS_DIR / "latest"
            if latest_link.exists() or latest_link.is_symlink():
                backup_dir = BACKUPS_DIR / latest_link.readlink()
            else:
                # Fallback to newest backup
                backup_dir = backups[0] if backups else None
        else:
            # Try to find by name
            for backup in backups:
                if backup.name == args.backup or str(backup) == args.backup:
                    backup_dir = backup
                    break
            
            if not backup_dir:
                # Try as path
                backup_path = Path(args.backup)
                if backup_path.exists() and backup_path.is_dir():
                    backup_dir = backup_path
    else:
        # Interactive selection
        print("\nAvailable backups:\n")
        for i, backup in enumerate(backups, 1):
            manifest = load_manifest(backup)
            if manifest:
                timestamp = manifest.get('backup_timestamp', backup.name)
                date = manifest.get('backup_date', 'unknown')
                count = manifest.get('strategy_count', '?')
                running = manifest.get('running_strategies_count', 0)
                print(f"  {i}. {timestamp} ({date[:10]}) - {count} strategies ({running} running)")
            else:
                print(f"  {i}. {backup.name}")
        
        print(f"\n  0. Cancel")
        
        try:
            choice = input("\nSelect backup to restore (number): ").strip()
            if choice == "0":
                print("Cancelled.")
                return 0
            
            index = int(choice) - 1
            if 0 <= index < len(backups):
                backup_dir = backups[index]
            else:
                print("Invalid selection.")
                return 1
        except (ValueError, KeyboardInterrupt):
            print("\nCancelled.")
            return 1
    
    if not backup_dir or not backup_dir.exists():
        print(f"❌ Backup not found: {args.backup if args.backup else 'selected backup'}")
        return 1
    
    # Dry run mode
    if args.dry_run:
        manifest = load_manifest(backup_dir)
        print(f"\n{'='*60}")
        print(f"DRY RUN - Preview of restore")
        print(f"{'='*60}")
        print(f"Backup: {backup_dir.name}")
        if manifest:
            print(f"Files in backup: {', '.join(manifest.get('files_backed_up', []))}")
        print(f"\nWould restore:")
        if (backup_dir / "strategy_configs.json").exists():
            print(f"  ✅ strategy_configs.json")
        if (backup_dir / "strategy_env.json").exists():
            print(f"  ✅ strategy_env.json")
        if args.include_env and (backup_dir / ".env").exists():
            print(f"  ✅ .env")
        print(f"\nProcess state reset: {'No' if args.no_reset_processes else 'Yes'}")
        print(f"{'='*60}\n")
        return 0
    
    # Warn about .env restore
    if args.include_env:
        print("\n⚠️  WARNING: .env file contains sensitive credentials (API keys, secrets)")
        print("   Restoring .env will overwrite your current server configuration.")
        response = input("Continue with .env restore? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            print("Skipping .env restore.")
            args.include_env = False
    
    # Perform restore
    success = restore_backup(
        backup_dir,
        reset_processes=not args.no_reset_processes,
        include_env=args.include_env
    )
    
    if success:
        print(f"✅ Restore completed successfully!")
        print(f"\nNext steps:")
        print(f"  1. Review restored files:")
        print(f"     - {STRATEGY_CONFIGS_FILE}")
        print(f"     - {STRATEGY_ENV_FILE}")
        if args.include_env:
            print(f"     - {ENV_FILE}")
        print(f"  2. Restart the server if .env was restored:")
        print(f"     python3 app.py")
        print(f"  3. Start strategies via web UI:")
        print(f"     http://127.0.0.1:5001/python/")
        return 0
    else:
        print(f"❌ Restore failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
