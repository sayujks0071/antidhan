#!/usr/bin/env python3
import sys
import os
import httpx
import datetime
import socket
import json
import warnings

# Suppress warnings from database drivers etc.
warnings.filterwarnings("ignore")

# Determine app root and change working directory to it
# This ensures relative paths in .env (like sqlite DB path) work correctly
app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if os.getcwd() != app_root:
    try:
        os.chdir(app_root)
        print(f"Changed working directory to: {app_root}")
    except Exception as e:
        print(f"Warning: Could not change working directory: {e}")

# Add openalgo directory to path
sys.path.append(app_root)

# Load environment variables
from utils.env_check import load_and_check_env_variables

# Wrap env check to handle potential exit
try:
    load_and_check_env_variables()
except SystemExit:
    print("Environment check failed. Please fix .env issues.")
    sys.exit(1)

from database.auth_db import Auth, db_session, get_api_key_for_tradingview

def check_port(host, port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            result = s.connect_ex((host, port))
            return result == 0
    except Exception:
        return False

def get_broker_api_key(broker_name):
    # Find a user with this broker
    try:
        # Query DB for ANY user with this broker that is not revoked
        auth_obj = Auth.query.filter_by(broker=broker_name, is_revoked=False).first()
        if auth_obj:
            user_id = auth_obj.user_id
            if user_id:
                api_key = get_api_key_for_tradingview(user_id)
                return api_key, auth_obj
        return None, None
    except Exception as e:
        print(f"Error querying DB for {broker_name}: {e}")
        return None, None

def check_api_connectivity(port, api_key):
    url = f"http://127.0.0.1:{port}/api/v1/funds"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, json={'apikey': api_key})
            if response.status_code == 200:
                return True, response.json(), None
            else:
                return False, response.json(), f"Status {response.status_code}"
    except Exception as e:
        return False, None, str(e)

def check_strategies():
    strategies_with_keys = 0
    auth_errors = []

    try:
        env_path = os.path.join(os.path.dirname(__file__), '../strategies/strategy_env.json')
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                strategy_env = json.load(f)
                # Assuming it maps strategy_name -> env_vars or similar structure
                if isinstance(strategy_env, dict):
                    for strategy, env in strategy_env.items():
                        if isinstance(env, dict) and env.get('API_KEY'):
                            strategies_with_keys += 1
                        elif isinstance(env, dict) and not env.get('API_KEY'):
                             auth_errors.append(f"{strategy}: Missing API_KEY")
    except Exception as e:
        auth_errors.append(f"Error reading strategy env: {str(e)}")

    return strategies_with_keys, auth_errors

def get_session_expiry():
    expiry_time = os.getenv('SESSION_EXPIRY_TIME', '03:00')
    try:
        hour, minute = map(int, expiry_time.split(':'))
        now = datetime.datetime.now()
        expiry = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # If current time is past expiry time, assume expiry is tomorrow
        # (Tokens are usually valid for the trading day until next morning)
        if now >= expiry:
            expiry += datetime.timedelta(days=1)
        return expiry.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "Unknown"

def generate_report():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    expiry_str = get_session_expiry()

    print(f"🔐 DAILY LOGIN HEALTH CHECK - {now}\n")

    # KITE CHECK
    print(f"✅ KITE CONNECT (Port 5001):")
    kite_port_open = check_port('127.0.0.1', 5001)
    print(f"- Server Status: {'✅ Running' if kite_port_open else '🔴 Down'}")

    kite_api_key, kite_auth = get_broker_api_key('zerodha')
    kite_connected = False

    if kite_port_open:
        if kite_api_key:
            success, data, error = check_api_connectivity(5001, kite_api_key)
            if success:
                 print(f"- Auth Token: ✅ Valid")
                 print(f"- Token Expiry: {expiry_str}")
                 print(f"- API Test: ✅ Connected")
                 kite_connected = True
            else:
                 print(f"- Auth Token: 🔴 Failed / Invalid")
                 print(f"- API Test: 🔴 Failed ({error})")
                 print(f"  -> Login URL: http://127.0.0.1:5001/auth/login")
        else:
            print(f"- Auth Token: ⚠️ Not Configured (No Zerodha user found)")
            print(f"  -> Login URL: http://127.0.0.1:5001/auth/login")
    else:
        if kite_api_key:
             print(f"- Auth Token: ❓ Found in DB but Server Down")
        print(f"- API Test: 🔴 Skipped (Server Down)")

    print("")

    # DHAN CHECK
    print(f"✅ DHAN API (Port 5002):")
    dhan_port_open = check_port('127.0.0.1', 5002)
    print(f"- Server Status: {'✅ Running' if dhan_port_open else '🔴 Down'}")

    dhan_api_key, dhan_auth = get_broker_api_key('dhan')

    if dhan_port_open:
        if dhan_api_key:
            success, data, error = check_api_connectivity(5002, dhan_api_key)
            if success:
                 print(f"- Access Token: ✅ Valid")
                 print(f"- Token Expiry: {expiry_str}")
                 print(f"- API Test: ✅ Connected")
            else:
                 print(f"- Access Token: 🔴 Failed / Invalid")
                 print(f"- API Test: 🔴 Failed ({error})")
                 print(f"  -> Login URL: http://127.0.0.1:5002/auth/login")
        else:
            print(f"- Access Token: ⚠️ Not Configured (No Dhan user found)")
            print(f"  -> Login URL: http://127.0.0.1:5002/auth/login")
    else:
        if dhan_api_key:
             print(f"- Access Token: ❓ Found in DB but Server Down")
        print(f"- API Test: 🔴 Skipped (Server Down)")

    print("")

    # OPENALGO AUTH
    print(f"✅ OPENALGO AUTH:")
    print(f"- Login Status: {'✅ Authenticated' if (kite_api_key or dhan_api_key) else '⚠️ No users found'}")

    strat_count, strat_errors = check_strategies()
    print(f"- API Keys: {strat_count} strategies configured")

    if strat_errors:
        print("\n⚠️ STRATEGY ISSUES DETECTED:")
        for err in strat_errors:
            print(f"- {err}")

    # Manual Actions Required
    print("\n📋 MANUAL ACTIONS REQUIRED:")
    manual_actions = False

    if not kite_port_open:
        print("- Start Kite server on port 5001")
        manual_actions = True
    if not dhan_port_open:
        print("- Start Dhan server on port 5002")
        manual_actions = True
    if kite_port_open and kite_api_key and not kite_connected:
        print("- Check Kite login/token validity")
        manual_actions = True

    if not manual_actions:
        print("- None ✅")

if __name__ == "__main__":
    generate_report()
