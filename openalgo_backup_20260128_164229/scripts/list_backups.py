#!/usr/bin/env python3
"""
List Available Backups

Shows all available backups with details from their manifests.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Paths
SCRIPT_DIR = Path(__file__).parent
OPENALGO_DIR = SCRIPT_DIR.parent
BACKUPS_DIR = OPENALGO_DIR / "backups"

def load_manifest(backup_dir: Path) -> Optional[Dict]:
    """Load backup manifest"""
    manifest_file = backup_dir / "backup_manifest.json"
    if not manifest_file.exists():
        return None
    
    try:
        with open(manifest_file, 'r') as f:
            return json.load(f)
    except Exception:
        return None

def list_backups() -> List[tuple[Path, Optional[Dict]]]:
    """List all available backups with their manifests"""
    if not BACKUPS_DIR.exists():
        return []
    
    backups = []
    for item in BACKUPS_DIR.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            manifest = load_manifest(item)
            backups.append((item, manifest))
    
    # Sort by directory name (timestamp) descending
    backups.sort(key=lambda x: x[0].name, reverse=True)
    return backups

def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

def get_backup_size(backup_dir: Path) -> int:
    """Calculate total size of backup directory"""
    total_size = 0
    try:
        for file_path in backup_dir.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
    except Exception:
        pass
    return total_size

def main():
    """Main entry point"""
    backups = list_backups()
    
    if not backups:
        print("No backups found.")
        print(f"\nCreate a backup with:")
        print(f"  python3 scripts/save_settings.py")
        return 0
    
    # Check for latest symlink
    latest_link = BACKUPS_DIR / "latest"
    latest_backup = None
    if latest_link.exists() or latest_link.is_symlink():
        try:
            latest_backup = BACKUPS_DIR / latest_link.readlink()
        except Exception:
            pass
    
    print(f"\n{'='*80}")
    print(f"Available Backups ({len(backups)} total)")
    print(f"{'='*80}\n")
    
    for i, (backup_dir, manifest) in enumerate(backups, 1):
        is_latest = (latest_backup and backup_dir == latest_backup)
        marker = " [LATEST]" if is_latest else ""
        
        if manifest:
            timestamp = manifest.get('backup_timestamp', backup_dir.name)
            date = manifest.get('backup_date', 'unknown')
            files = manifest.get('files_backed_up', [])
            strategy_count = manifest.get('strategy_count', '?')
            running_count = manifest.get('running_strategies_count', 0)
            version = manifest.get('openalgo_version', 'unknown')
            
            # Calculate size
            size = get_backup_size(backup_dir)
            size_str = format_size(size)
            
            print(f"{i}. {timestamp}{marker}")
            print(f"   Date: {date}")
            print(f"   Strategies: {strategy_count} total, {running_count} running")
            print(f"   Files: {', '.join(files)}")
            print(f"   Size: {size_str}")
            print(f"   Version: {version}")
            
            if manifest.get('errors'):
                print(f"   ⚠️  Errors: {len(manifest['errors'])}")
        else:
            # No manifest - show basic info
            print(f"{i}. {backup_dir.name}{marker}")
            print(f"   (No manifest file)")
            size = get_backup_size(backup_dir)
            size_str = format_size(size)
            print(f"   Size: {size_str}")
        
        print()
    
    print(f"{'='*80}")
    print(f"\nTo restore a backup:")
    print(f"  python3 scripts/restore_settings.py")
    print(f"\nTo restore latest backup:")
    print(f"  python3 scripts/restore_settings.py --backup latest")
    print(f"\nTo create a new backup:")
    print(f"  python3 scripts/save_settings.py")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
