#!/usr/bin/env python3
import os
import sys

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Also add openalgo/scripts to path if needed for internal imports within daily_prep
scripts_dir = os.path.join(repo_root, 'openalgo', 'scripts')
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

try:
    from openalgo.scripts.daily_prep import fetch_instruments
except ImportError:
    # Fallback if openalgo package is not directly importable (e.g. not installed)
    sys.path.insert(0, os.path.join(repo_root, 'openalgo'))
    from scripts.daily_prep import fetch_instruments

def main():
    print("🔄 Syncing instruments...")
    try:
        fetch_instruments()
        print("✅ Instruments synced.")
    except Exception as e:
        print(f"❌ Failed to sync instruments: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
