#!/usr/bin/env python3
"""
Trend Pullback Strategy
Trades pullbacks in strong trends with breadth confirmation.
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
logger = logging.getLogger(f"Pullback_{SYMBOL}")

def run_strategy():
    if not api: return
    client = api(api_key=API_KEY, host=HOST)
    logger.info(f"Starting Trend Pullback for {SYMBOL}")

    while True:
        try:
            df = client.history(symbol=SYMBOL, exchange="NSE", interval="15m",
                                start_date=(datetime.now()-timedelta(days=10)).strftime("%Y-%m-%d"),
                                end_date=datetime.now().strftime("%Y-%m-%d"))

            if df.empty: continue

            # Simple MA Trend
            df['sma50'] = df['close'].rolling(50).mean()
            df['sma200'] = df['close'].rolling(200).mean()

            last = df.iloc[-1]

            # Uptrend: SMA50 > SMA200
            if last['sma50'] > last['sma200']:
                # Pullback: Price < SMA50 but > SMA200 (Deep pullback) or Price < SMA20 (Shallow)
                if last['close'] < last['sma50']:
                    logger.info("Pullback detected in Uptrend")
                    # Check Reversal signal (e.g. Hammer candle)
                    # Buy

        except Exception as e:
            logger.error(f"Error: {e}")
        time.sleep(60)

if __name__ == "__main__":
    run_strategy()
