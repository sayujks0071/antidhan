#!/usr/bin/env python3
import sys
import os
import time
import requests
import socket
import logging
import json

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Add openalgo directory to path
openalgo_root = os.path.join(repo_root, 'openalgo')
if openalgo_root not in sys.path:
    sys.path.insert(0, openalgo_root)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("LoginDebug")

from openalgo.utils.env_check import load_and_check_env_variables

# 1. Allow env check to fail loudly if configured incorrectly (Code Review Feedback)
load_and_check_env_variables()

try:
    from openalgo.database.auth_db import get_auth_token_dbquery, Auth, db_session, decrypt_token
    DB_AVAILABLE = True
except ImportError:
    logger.error("DB Module Import Failed")
    DB_AVAILABLE = False
except Exception as e:
    logger.error(f"DB Error: {e}")
    DB_AVAILABLE = False

def check_port(port, host='127.0.0.1'):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex((host, port)) == 0
    except:
        return False

def check_kite_login():
    """Debug Kite Login Status"""
    print("\n🔍 Checking Kite Login...")
    status = {"server": False, "token": False, "api": False, "error": None}

    # 1. Test Server
    if check_port(5001):
        status["server"] = True
        print("✅ Kite Server (Port 5001): Running")
    else:
        status["error"] = "Server Down"
        print("🔴 Kite Server (Port 5001): Down")
        return status

    # 2. Check Token
    if DB_AVAILABLE:
        try:
            auth = Auth.query.filter_by(broker='zerodha', is_revoked=False).first()
            if auth:
                status["token"] = True
                print("✅ Auth Token: Found in DB")
            else:
                status["error"] = "Token Missing/Expired"
                print("🔴 Auth Token: Missing/Expired")
                return status
        except Exception as e:
            status["error"] = f"DB Error: {e}"
            print(f"🔴 Auth Token: DB Error ({e})")
            return status
    else:
        status["error"] = "DB Unavailable"
        print("🔴 Auth Token: DB Unavailable")
        return status

    # 3. Test API
    try:
        resp = requests.get("http://127.0.0.1:5001/api/v1/user/profile", timeout=2)
        if resp.status_code == 200:
            status["api"] = True
            print("✅ API Connectivity: OK")
        else:
            status["error"] = f"API Error {resp.status_code}"
            print(f"🔴 API Connectivity: Failed ({resp.status_code})")
    except Exception as e:
        status["error"] = str(e)
        print(f"🔴 API Connectivity: Error ({e})")

    return status

def check_dhan_login():
    """Debug Dhan Login Status"""
    print("\n🔍 Checking Dhan Login...")
    status = {"server": False, "token": False, "api": False, "error": None}

    # 1. Test Server
    if check_port(5002):
        status["server"] = True
        print("✅ Dhan Server (Port 5002): Running")
    else:
        status["error"] = "Server Down"
        print("🔴 Dhan Server (Port 5002): Down")
        return status

    # 2. Check Token
    if DB_AVAILABLE:
        try:
            auth = Auth.query.filter_by(broker='dhan', is_revoked=False).first()
            if auth:
                status["token"] = True
                print("✅ Auth Token: Found in DB")
            else:
                status["error"] = "Token Missing/Expired"
                print("🔴 Auth Token: Missing/Expired")
                return status
        except Exception as e:
            status["error"] = f"DB Error: {e}"
            print(f"🔴 Auth Token: DB Error ({e})")
            return status
    else:
        status["error"] = "DB Unavailable"
        print("🔴 Auth Token: DB Unavailable")
        return status

    # 3. Test API
    try:
        resp = requests.get("http://127.0.0.1:5002/api/v1/user/profile", timeout=2)
        if resp.status_code == 200:
            status["api"] = True
            print("✅ API Connectivity: OK")
        else:
            status["error"] = f"API Error {resp.status_code}"
            print(f"🔴 API Connectivity: Failed ({resp.status_code})")
    except Exception as e:
        status["error"] = str(e)
        print(f"🔴 API Connectivity: Error ({e})")

    return status

def check_strategy_auth():
    """Debug Strategy Auth Config"""
    print("\n🔍 Checking Strategy Auth...")
    config_file = os.path.join(repo_root, 'openalgo/strategies/active_strategies.json')
    if not os.path.exists(config_file):
        print("🔴 Active Strategies Config: Missing")
        return

    try:
        with open(config_file, 'r') as f:
            strategies = json.load(f)

        count = len(strategies)
        print(f"✅ Active Strategies Config: Found ({count} strategies)")

        # Verify if API keys are set (conceptually, usually handled by env vars or DB)
        # Here we just check if they are loaded
        valid = True
        for name, data in strategies.items():
            if not data.get('strategy'):
                print(f"⚠️  Strategy {name}: Missing 'strategy' script name")
                valid = False

        if valid:
             print("✅ Strategy Configuration: Valid")

    except Exception as e:
        print(f"🔴 Strategy Config Error: {e}")

def generate_auth_url(broker):
    # 2. Improve generated URL logic (Code Review Feedback)
    api_key = os.getenv("BROKER_API_KEY", "YOUR_API_KEY")

    # Handle composite keys (e.g. client_id:::api_key)
    if ":::" in api_key:
        parts = api_key.split(":::")
        if len(parts) >= 2:
            api_key = parts[1]
            client_id = parts[0]

    if broker == 'zerodha':
        return f"https://kite.zerodha.com/connect/login?v=3&api_key={api_key}"
    elif broker == 'dhan':
        # Dhan usually uses client ID for login initiation
        return "https://auth.dhan.co/login"
    return "#"

def auto_fix_login_issues():
    """Attempt to resolve common login issues"""
    print("\n🛠️  Attempting Auto-Fix...")

    kite_status = check_kite_login()
    if kite_status["error"]:
        print(f"⚠️  Kite Issue: {kite_status['error']}")
        if "Token" in kite_status["error"]:
            url = generate_auth_url('zerodha')
            print(f"👉 ACTION: Re-authenticate at {url}")
        elif "Server" in kite_status["error"]:
            print("👉 ACTION: Start the Kite Server (port 5001)")

    dhan_status = check_dhan_login()
    if dhan_status["error"]:
        print(f"⚠️  Dhan Issue: {dhan_status['error']}")
        if "Token" in dhan_status["error"]:
            url = generate_auth_url('dhan')
            print(f"👉 ACTION: Re-authenticate at {url}")
        elif "Server" in dhan_status["error"]:
            print("👉 ACTION: Start the Dhan Server (port 5002)")

    check_strategy_auth()

    if not kite_status["error"] and not dhan_status["error"]:
        print("\n✅ No critical login issues found requiring auto-fix.")

if __name__ == "__main__":
    print("🚀 Login Debugger Started")
    auto_fix_login_issues()
    print("\n🏁 Debug Complete")
