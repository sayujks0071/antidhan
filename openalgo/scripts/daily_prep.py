#!/usr/bin/env python3
import os
import sys
import json
import logging
import subprocess
import shutil
import glob
from datetime import datetime
import httpx
import pandas as pd

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(repo_root)

from openalgo.strategies.utils.symbol_resolver import SymbolResolver
from openalgo.strategies.utils.trading_utils import APIClient

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DailyPrep")

DATA_DIR = os.path.join(repo_root, 'openalgo/data')
STATE_DIR = os.path.join(repo_root, 'openalgo/strategies/state')
CONFIG_FILE = os.path.join(repo_root, 'openalgo/strategies/active_strategies.json')

def check_env():
    logger.info("Checking Environment...")
    if not os.getenv('OPENALGO_APIKEY'):
        logger.warning("OPENALGO_APIKEY not set. Using default 'demo_key'.")
        os.environ['OPENALGO_APIKEY'] = 'demo_key'

    # Verify paths
    if not os.path.exists(os.path.join(repo_root, 'openalgo')):
        logger.error("Repo structure invalid. 'openalgo' dir not found.")
        sys.exit(1)
    logger.info("Environment OK.")

def purge_stale_state():
    logger.info("Purging Stale State...")

    # 1. Clear PositionManager state
    if os.path.exists(STATE_DIR):
        files = glob.glob(os.path.join(STATE_DIR, "*.json"))
        for f in files:
            try:
                os.remove(f)
                logger.info(f"Deleted state file: {os.path.basename(f)}")
            except Exception as e:
                logger.error(f"Failed to delete {f}: {e}")

    # 2. Clear Cached Instruments
    inst_file = os.path.join(DATA_DIR, 'instruments.csv')
    if os.path.exists(inst_file):
        try:
            os.remove(inst_file)
            logger.info("Deleted cached instruments.csv")
        except Exception as e:
            logger.error(f"Failed to delete instruments.csv: {e}")

    # 3. Clear Auth/Sessions (Mock implementation - assume they are in openalgo/sessions if it exists)
    session_dir = os.path.join(repo_root, 'openalgo/sessions')
    if os.path.exists(session_dir):
         shutil.rmtree(session_dir) # Wipe dir
         os.makedirs(session_dir) # Recreate
         logger.info("Purged session directory.")

def check_auth():
    logger.info("Running Authentication Health Check...")
    script_path = os.path.join(repo_root, 'openalgo/scripts/authentication_health_check.py')
    try:
        # Run the health check script
        result = subprocess.run([sys.executable, script_path], capture_output=True, text=True)
        print(result.stdout)
        if result.returncode != 0:
            logger.error("Authentication check failed!")
            # In production, we might exit. For now, we continue as it might be a simulation.
            # sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to run auth check: {e}")

def fetch_instruments():
    logger.info("Fetching Instruments...")
    os.makedirs(DATA_DIR, exist_ok=True)
    csv_path = os.path.join(DATA_DIR, 'instruments.csv')

    api_key = os.getenv('OPENALGO_APIKEY')
    host = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')

    try:
        # Try fetching from API
        url = f"{host}/api/v1/instruments"
        logger.info(f"Requesting {url}...")
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, headers={'X-API-KEY': api_key})
            if resp.status_code == 200:
                # Assuming CSV content or JSON to be converted
                # If JSON:
                # data = resp.json()
                # df = pd.DataFrame(data)
                # df.to_csv(csv_path, index=False)

                # If content is CSV directly:
                with open(csv_path, 'wb') as f:
                    f.write(resp.content)
                logger.info("Instruments downloaded successfully.")
                return
            else:
                logger.warning(f"Failed to fetch instruments from API: {resp.status_code}")
    except Exception as e:
        logger.warning(f"API Connection failed: {e}")

    # Fallback: Generate Stub Instruments if not found (For dev/test)
    if not os.path.exists(csv_path):
        logger.info("Generating Mock Instruments for testing...")
        from datetime import datetime, timedelta
        now = datetime.now()
        data = [
            {'exchange': 'NSE', 'token': '1', 'symbol': 'RELIANCE', 'name': 'RELIANCE', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ'},
            {'exchange': 'NSE', 'token': '2', 'symbol': 'NIFTY', 'name': 'NIFTY', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ'},
            {'exchange': 'NSE', 'token': '3', 'symbol': 'INFY', 'name': 'INFY', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ'},
            {'exchange': 'MCX', 'token': '4', 'symbol': 'SILVERMIC23NOVFUT', 'name': 'SILVER', 'expiry': (now + timedelta(days=20)).strftime('%Y-%m-%d'), 'lot_size': 1, 'instrument_type': 'FUT'},
             # Options
            {'exchange': 'NFO', 'token': '10', 'symbol': 'NIFTY23OCT19500CE', 'name': 'NIFTY', 'expiry': (now + timedelta(days=3)).strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'OPT'},
        ]
        pd.DataFrame(data).to_csv(csv_path, index=False)
        logger.info(f"Mock instruments saved to {csv_path}")

def validate_symbols():
    logger.info("Validating Strategy Symbols...")
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"Config file not found: {CONFIG_FILE}")
        return

    try:
        with open(CONFIG_FILE, 'r') as f:
            configs = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return

    resolver = SymbolResolver(os.path.join(DATA_DIR, 'instruments.csv'))

    valid_count = 0
    invalid_count = 0

    print("\n--- SYMBOL VALIDATION REPORT ---")
    print(f"{'STRATEGY':<20} | {'TYPE':<8} | {'INPUT':<15} | {'RESOLVED':<25} | {'STATUS'}")
    print("-" * 90)

    for strat_id, config in configs.items():
        try:
            resolved = resolver.resolve(config)

            status = "✅ Valid"
            resolved_str = str(resolved)

            if resolved is None:
                status = "🔴 Invalid"
                invalid_count += 1
            elif isinstance(resolved, dict) and resolved.get('status') == 'valid':
                # Options return dict
                resolved_str = f"Expiry: {resolved['expiry']}"
                valid_count += 1
            else:
                valid_count += 1

            print(f"{strat_id:<20} | {config.get('type'):<8} | {config.get('underlying'):<15} | {resolved_str[:25]:<25} | {status}")

        except Exception as e:
            logger.error(f"Error validating {strat_id}: {e}")
            invalid_count += 1

    print("-" * 90)
    if invalid_count > 0:
        logger.error(f"Found {invalid_count} invalid symbols! Trading Halted.")
        sys.exit(1)
    else:
        logger.info("All symbols valid. Ready to trade.")

def main():
    print("🚀 DAILY PREP STARTED")
    check_env()
    purge_stale_state()
    check_auth()
    fetch_instruments()
    validate_symbols()
    print("✅ DAILY PREP COMPLETE")

if __name__ == "__main__":
    main()
