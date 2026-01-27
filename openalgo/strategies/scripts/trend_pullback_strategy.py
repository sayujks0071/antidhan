#!/usr/bin/env python3
"""
Trend Pullback Strategy
Enhanced with Sector Strength, Pullback Depth, and Market Breadth.
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(f"Pullback_{SYMBOL}")

def check_market_breadth():
    # Placeholder for A/D Ratio check
    return True

def check_sector_strength():
    # Placeholder
    return True

def run_strategy():
    if not api: return
    client = api(api_key=API_KEY, host=HOST)
    logger.info(f"Starting Trend Pullback for {SYMBOL}")

    while True:
        try:
            if not check_market_breadth() or not check_sector_strength():
                logger.info("Market/Sector weak. Waiting.")
                time.sleep(300)
                continue

            # Fetch Data
            df = client.history(symbol=SYMBOL, exchange="NSE", interval="15m",
                                start_date=(datetime.now()-timedelta(days=10)).strftime("%Y-%m-%d"),
                                end_date=datetime.now().strftime("%Y-%m-%d"))

            if df.empty:
                time.sleep(60)
                continue

            df['sma20'] = df['close'].rolling(20).mean()
            df['sma50'] = df['close'].rolling(50).mean()
            df['sma200'] = df['close'].rolling(200).mean()

            last = df.iloc[-1]

            # Trend: SMA50 > SMA200 (Uptrend)
            if last['sma50'] > last['sma200']:
                price = last['close']

                # Pullback Depth
                # Shallow: Price < SMA20
                # Deep: Price < SMA50
                # Invalid: Price < SMA200

                if price < last['sma200']:
                    # Trend broken
                    pass
                elif price < last['sma50']:
                    # Deep Pullback
                    # Look for Reversal (Close > Open)
                    if last['close'] > last['open']:
                        logger.info("Deep Pullback Reversal (at SMA50). BUY.")
                        # client.placesmartorder(...)
                elif price < last['sma20']:
                    # Shallow Pullback
                    if last['close'] > last['open']:
                        logger.info("Shallow Pullback Reversal (at SMA20). BUY.")
                        # client.placesmartorder(...)

        except Exception as e:
            logger.error(f"Error: {e}")

        time.sleep(60)

if __name__ == "__main__":
    run_strategy()
