#!/usr/bin/env python3
"""
Diagnose why start buttons might not be working.
"""
import json
import os
from pathlib import Path
import subprocess

CONFIG_PATH = Path("/Users/mac/dyad-apps/openalgo/strategies/strategy_configs.json")
BASE_DIR = Path("/Users/mac/dyad-apps/openalgo")

def check_master_contracts():
    """Check master contract status."""
    try:
        from database.master_contract_status_db import check_if_ready
        # Try to get broker from session or use default
        broker = os.environ.get('BROKER', 'zerodha')
        is_ready = check_if_ready(broker)
        return is_ready, broker
    except Exception as e:
        return None, f"Error checking: {str(e)}"

def check_file_exists(file_path):
    """Check if strategy file exists."""
    full_path = BASE_DIR / file_path
    return full_path.exists(), str(full_path)

def check_file_permissions(file_path):
    """Check file permissions."""
    full_path = BASE_DIR / file_path
    if not full_path.exists():
        return False, "File does not exist"
    
    readable = os.access(full_path, os.R_OK)
    executable = os.access(full_path, os.X_OK)
    
    return readable, f"Readable: {readable}, Executable: {executable}"

def main():
    print("=" * 80)
    print("START BUTTON DIAGNOSTICS")
    print("=" * 80)
    
    if not CONFIG_PATH.exists():
        print("❌ Strategy configs not found")
        return
    
    configs = json.loads(CONFIG_PATH.read_text())
    
    # Check master contracts
    print("\n1. Master Contract Status:")
    mc_ready, mc_info = check_master_contracts()
    if mc_ready is True:
        print(f"   ✅ Master contracts ready for broker: {mc_info}")
    elif mc_ready is False:
        print(f"   ⚠️  Master contracts NOT ready for broker: {mc_info}")
        print("   This will prevent strategies from starting!")
    else:
        print(f"   ⚠️  Could not check: {mc_info}")
    
    # Check each stopped strategy
    print("\n2. Checking Stopped Strategies:")
    stopped = [(k, v) for k, v in configs.items() if not v.get('is_running')]
    
    if not stopped:
        print("   ✅ All strategies are running")
        return
    
    issues_found = []
    
    for strategy_id, config in stopped:
        name = config.get('name', strategy_id)
        file_path = config.get('file_path', '')
        
        print(f"\n   Strategy: {name} ({strategy_id})")
        
        # Check file exists
        exists, full_path = check_file_exists(file_path)
        if not exists:
            print(f"     ❌ File not found: {full_path}")
            issues_found.append(f"{name}: File not found")
            continue
        print(f"     ✅ File exists: {full_path}")
        
        # Check permissions
        readable, perm_info = check_file_permissions(file_path)
        if not readable:
            print(f"     ❌ Permission issue: {perm_info}")
            issues_found.append(f"{name}: {perm_info}")
        else:
            print(f"     ✅ Permissions OK: {perm_info}")
        
        # Check if file has shebang
        try:
            with open(full_path, 'r') as f:
                first_line = f.readline()
                if not first_line.startswith('#!'):
                    print(f"     ⚠️  No shebang line (not critical)")
        except Exception as e:
            print(f"     ⚠️  Could not read file: {e}")
    
    # Summary
    print("\n" + "=" * 80)
    if issues_found:
        print("ISSUES FOUND:")
        for issue in issues_found:
            print(f"  - {issue}")
        print("\nRECOMMENDATIONS:")
        if mc_ready is False:
            print("  1. Master contracts not ready - this blocks all strategy starts")
            print("     Go to: http://127.0.0.1:5001/python/")
            print("     Click 'Check & Start' button to initialize master contracts")
        print("  2. Check browser console (F12) for JavaScript errors")
        print("  3. Check server logs for detailed error messages")
        print("  4. Try refreshing the page (Ctrl+R or Cmd+R)")
    else:
        print("✅ No obvious issues found")
        print("\nIf buttons still don't work:")
        print("  1. Check browser console (F12) for JavaScript errors")
        print("  2. Check if CSRF token is present in page source")
        print("  3. Check server logs: tail -f log/*.log")
        print("  4. Try clearing browser cache and reloading")
    
    print("=" * 80)

if __name__ == "__main__":
    main()
