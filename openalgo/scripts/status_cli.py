#!/usr/bin/env python3
"""
Quick status CLI for OpenAlgo live trading system.
"""
import json
import subprocess
from pathlib import Path
from datetime import datetime

def get_ist_time():
    """Get current IST time."""
    return datetime.now().strftime("%H:%M:%S IST")

def check_strategies():
    """Check running strategies."""
    config_path = Path("/Users/mac/dyad-apps/openalgo/strategies/strategy_configs.json")
    if not config_path.exists():
        return []
    
    configs = json.loads(config_path.read_text())
    running = []
    for sid, cfg in configs.items():
        if cfg.get('is_running'):
            pid = cfg.get('pid')
            name = cfg.get('name', sid)
            # Check if process is actually running
            is_active = False
            if pid:
                try:
                    result = subprocess.run(['ps', '-p', str(pid)], 
                                          capture_output=True, text=True)
                    is_active = result.returncode == 0
                except:
                    pass
            running.append({
                'name': name,
                'pid': pid,
                'active': is_active
            })
    return running

def check_broker_auth():
    """Check broker authentication status."""
    try:
        import sqlite3
        conn = sqlite3.connect('/Users/mac/dyad-apps/openalgo/db/openalgo.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT broker, auth_token, is_revoked, updated_at 
            FROM auth 
            WHERE is_revoked = 0 
            ORDER BY id DESC 
            LIMIT 1
        ''')
        row = cursor.fetchone()
        conn.close()
        
        if row:
            broker, token, revoked, updated = row
            return {
                'broker': broker,
                'token_length': len(token) if token else 0,
                'revoked': bool(revoked),
                'updated': updated
            }
    except Exception as e:
        return {'error': str(e)}
    return None

def main():
    print("=" * 80)
    print("OPENALGO LIVE TRADING STATUS")
    print("=" * 80)
    print(f"Time: {get_ist_time()}")
    print()
    
    # Check broker auth
    print("🔐 Broker Authentication:")
    auth = check_broker_auth()
    if auth and 'error' not in auth:
        print(f"  Broker: {auth.get('broker', 'Unknown')} ✅")
        print(f"  Token: {auth.get('token_length', 0)} bytes ✅")
        print(f"  Revoked: {'No' if not auth.get('revoked') else 'Yes'} ✅")
        print(f"  Updated: {auth.get('updated', 'Unknown')}")
    else:
        print("  ⚠️  Could not check auth status")
    print()
    
    # Check strategies
    print("📊 Running Strategies:")
    strategies = check_strategies()
    if strategies:
        for s in strategies:
            status = "✅ ACTIVE" if s['active'] else "⚠️  INACTIVE"
            print(f"  {s['name']} (PID: {s['pid']}) - {status}")
    else:
        print("  ⚠️  No running strategies found")
    print()
    
    # Market status
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    market_open = (hour == 9 and minute >= 15) or (9 < hour < 15) or (hour == 15 and minute <= 30)
    print("📈 Market Status:")
    if market_open:
        print("  Market: OPEN ✅")
        print("  Hours: 9:15 AM - 3:30 PM IST")
    else:
        print("  Market: CLOSED")
    print()
    
    print("=" * 80)
    print(f"✅ System Status: {'OPERATIONAL' if strategies and auth else 'CHECK REQUIRED'}")
    print("=" * 80)

if __name__ == "__main__":
    main()
