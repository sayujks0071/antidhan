#!/usr/bin/env python3
"""
Sector Momentum Strategy
Trades stocks in strongest sectors.
"""
import os
import time
import logging
import pandas as pd
from datetime import datetime, timedelta

try:
    from openalgo import api
except ImportError:
    api = None

SYMBOL = "REPLACE_ME"
API_KEY = os.getenv('OPENALGO_APIKEY', 'demo_key')
HOST = os.getenv('OPENALGO_HOST', 'http://127.0.0.1:5001')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(f"SectorMom_{SYMBOL}")

def run_strategy():
    if not api: return
    client = api(api_key=API_KEY, host=HOST)
    logger.info(f"Starting Sector Momentum for {SYMBOL}")

    while True:
        try:
            # 1. Verify Sector Strength (Ideally passed or fetched)
            # Assuming SYMBOL belongs to a Strong Sector (pre-filtered by advanced_equity_strategy.py)

            # 2. Check Stock Momentum
            df = client.history(symbol=SYMBOL, exchange="NSE", interval="1h",
                                start_date=(datetime.now()-timedelta(days=20)).strftime("%Y-%m-%d"),
                                end_date=datetime.now().strftime("%Y-%m-%d"))

            if df.empty: continue

            # RS logic: Compare stock return to Index return (if available)
            # Simple Momentum: Price > SMA20 and RSI > 60
            df['sma20'] = df['close'].rolling(20).mean()
            # RSI calc omitted for brevity

            last = df.iloc[-1]
            if last['close'] > last['sma20']:
                logger.info("Stock confirming Sector Momentum")
                # Buy

        except Exception as e:
            logger.error(f"Error: {e}")
        time.sleep(60)

if __name__ == "__main__":
    run_strategy()
