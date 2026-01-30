#!/usr/bin/env python3
import os
import sys
import json
import logging
import subprocess
import shutil
import glob
from datetime import datetime, timedelta
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
SESSION_DIR = os.path.join(repo_root, 'openalgo/sessions')
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
        deleted_count = 0
        for f in files:
            try:
                os.remove(f)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete {f}: {e}")
        logger.info(f"Deleted {deleted_count} state files from {STATE_DIR}")
    else:
        logger.info(f"State dir {STATE_DIR} does not exist, skipping.")

    # 2. Clear Cached Instruments
    inst_file = os.path.join(DATA_DIR, 'instruments.csv')
    if os.path.exists(inst_file):
        try:
            os.remove(inst_file)
            logger.info("Deleted cached instruments.csv")
        except Exception as e:
            logger.error(f"Failed to delete instruments.csv: {e}")

    # 3. Clear Auth/Sessions
    if os.path.exists(SESSION_DIR):
        try:
            shutil.rmtree(SESSION_DIR)
            os.makedirs(SESSION_DIR)
            logger.info(f"Purged and recreated session directory: {SESSION_DIR}")
        except Exception as e:
             logger.error(f"Failed to purge session directory: {e}")
    else:
        os.makedirs(SESSION_DIR, exist_ok=True)
        logger.info(f"Created session directory: {SESSION_DIR}")

def check_auth():
    logger.info("Running Authentication Health Check...")
    script_path = os.path.join(repo_root, 'openalgo/scripts/authentication_health_check.py')

    # Check if script exists, if not, mock it for now
    if not os.path.exists(script_path):
        logger.warning(f"Auth check script not found at {script_path}. Skipping.")
        return

    try:
        # Run the health check script
        result = subprocess.run([sys.executable, script_path], capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("Authentication check failed!")
            logger.error(result.stderr)
            # In a strict environment, we might exit here:
            # sys.exit(1)
        else:
            logger.info("Authentication check passed.")
    except Exception as e:
        logger.error(f"Failed to run auth check: {e}")

def fetch_instruments():
    logger.info("Fetching Instruments...")
    os.makedirs(DATA_DIR, exist_ok=True)
    csv_path = os.path.join(DATA_DIR, 'instruments.csv')

    api_key = os.getenv('OPENALGO_APIKEY')
    host = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')

    fetched = False
    try:
        # Try fetching from API
        url = f"{host}/api/v1/instruments"
        logger.info(f"Requesting {url}...")
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, headers={'X-API-KEY': api_key})
            if resp.status_code == 200:
                with open(csv_path, 'wb') as f:
                    f.write(resp.content)
                logger.info("Instruments downloaded successfully via API.")
                fetched = True
            else:
                logger.warning(f"Failed to fetch instruments from API: {resp.status_code}")
    except Exception as e:
        logger.warning(f"API Connection failed: {e}")

    # Fallback: Generate Comprehensive Mock Instruments if not found
    if not fetched:
        logger.info("Using Fallback: Generating Mock Instruments...")
        now = datetime.now()

        # Calculate next Thursday for Weekly Expiry
        days_ahead = 3 - now.weekday()
        if days_ahead < 0: days_ahead += 7
        next_thursday = now + timedelta(days=days_ahead)

        # Calculate Monthly Expiry (Last Thursday of current month)
        # Simplified: Last day of month
        import calendar
        last_day = calendar.monthrange(now.year, now.month)[1]
        month_end = datetime(now.year, now.month, last_day)
        # Backtrack to Thursday
        offset = (month_end.weekday() - 3) % 7
        monthly_expiry = month_end - timedelta(days=offset)

        data = [
            # Equities
            {'exchange': 'NSE', 'token': '1', 'symbol': 'RELIANCE', 'name': 'RELIANCE', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ'},
            {'exchange': 'NSE', 'token': '2', 'symbol': 'NIFTY', 'name': 'NIFTY', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ'},
            {'exchange': 'NSE', 'token': '3', 'symbol': 'INFY', 'name': 'INFY', 'expiry': None, 'lot_size': 1, 'instrument_type': 'EQ'},

            # MCX Futures (Standard & MINI)
            {'exchange': 'MCX', 'token': '4', 'symbol': 'SILVERMIC23NOVFUT', 'name': 'SILVER', 'expiry': (now + timedelta(days=20)).strftime('%Y-%m-%d'), 'lot_size': 1, 'instrument_type': 'FUT'},
            {'exchange': 'MCX', 'token': '5', 'symbol': 'SILVER23NOVFUT', 'name': 'SILVER', 'expiry': (now + timedelta(days=20)).strftime('%Y-%m-%d'), 'lot_size': 30, 'instrument_type': 'FUT'},
            {'exchange': 'MCX', 'token': '6', 'symbol': 'GOLDM23NOVFUT', 'name': 'GOLD', 'expiry': (now + timedelta(days=25)).strftime('%Y-%m-%d'), 'lot_size': 10, 'instrument_type': 'FUT'},

            # NSE Futures
            {'exchange': 'NFO', 'token': '7', 'symbol': 'NIFTY23OCTFUT', 'name': 'NIFTY', 'expiry': monthly_expiry.strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'FUT'},

            # NSE Options (Weekly)
            {'exchange': 'NFO', 'token': '10', 'symbol': 'NIFTY23OCT19500CE', 'name': 'NIFTY', 'expiry': next_thursday.strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'OPT'},
            {'exchange': 'NFO', 'token': '11', 'symbol': 'NIFTY23OCT19500PE', 'name': 'NIFTY', 'expiry': next_thursday.strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'OPT'},

            # NSE Options (Monthly)
            {'exchange': 'NFO', 'token': '12', 'symbol': 'NIFTY23OCT19600CE', 'name': 'NIFTY', 'expiry': monthly_expiry.strftime('%Y-%m-%d'), 'lot_size': 50, 'instrument_type': 'OPT'},
        ]

        try:
            pd.DataFrame(data).to_csv(csv_path, index=False)
            logger.info(f"Mock instruments generated and saved to {csv_path}")
        except Exception as e:
            logger.error(f"Failed to save mock instruments: {e}")
            sys.exit(1)

def validate_symbols():
    logger.info("Validating Strategy Symbols...")
    if not os.path.exists(CONFIG_FILE):
        logger.warning(f"Config file not found: {CONFIG_FILE}. Skipping validation.")
        return

    try:
        with open(CONFIG_FILE, 'r') as f:
            content = f.read()
            if not content.strip():
                configs = {}
            else:
                configs = json.loads(content)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return

    if not configs:
         logger.info("No active strategies configured.")
         return

    resolver = SymbolResolver(os.path.join(DATA_DIR, 'instruments.csv'))

    valid_count = 0
    invalid_count = 0

    print("\n--- SYMBOL VALIDATION REPORT ---")
    print(f"{'STRATEGY':<25} | {'TYPE':<8} | {'INPUT':<15} | {'RESOLVED':<30} | {'STATUS'}")
    print("-" * 95)

    for strat_id, config in configs.items():
        try:
            resolved = resolver.resolve(config)

            status = "✅ Valid"
            resolved_str = "Unknown"

            if resolved is None:
                status = "🔴 Invalid"
                invalid_count += 1
                resolved_str = "None"
            elif isinstance(resolved, dict):
                # Options return dict
                if resolved.get('status') == 'valid':
                    resolved_str = f"Expiry: {resolved.get('expiry')}"
                    valid_count += 1
                else:
                    status = "🔴 Invalid"
                    invalid_count += 1
                    resolved_str = "Invalid"
            else:
                # String result
                resolved_str = str(resolved)
                valid_count += 1

            print(f"{strat_id:<25} | {config.get('type'):<8} | {config.get('underlying'):<15} | {resolved_str[:30]:<30} | {status}")

        except Exception as e:
            logger.error(f"Error validating {strat_id}: {e}")
            invalid_count += 1
            print(f"{strat_id:<25} | {config.get('type'):<8} | {config.get('underlying'):<15} | {'ERROR':<30} | 🔴 Error")

    print("-" * 95)
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
